import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { writeFile, unlink } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { ESLint, Linter } from "eslint";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

const repositoryRoot = path.resolve(process.cwd(), "..");
const frontendRoot = path.join(repositoryRoot, "frontend");

interface BoundaryFixture {
  readonly relativePath: string;
  readonly carrierFile: string;
  readonly source: string;
  readonly expectedMessage: string;
  readonly expectedRule?: string;
  readonly expectedAdditionalArchitectureMessages?: readonly string[];
  readonly expectedArchitectureCount?: number;
  readonly expectedAdditionalRules?: readonly string[];
}

interface BoundaryFixtureSegment {
  readonly fixture: BoundaryFixture;
  readonly startLine: number;
  readonly endLine: number;
}

interface BoundaryFixtureGroup {
  readonly carrierFile: string;
  readonly source: string;
  readonly segments: readonly BoundaryFixtureSegment[];
}

interface NormalizedDiagnostic {
  readonly ruleId: string | null;
  readonly severity: number;
  readonly message: string;
  readonly line: number;
  readonly column: number;
  readonly endLine: number | null;
  readonly endColumn: number | null;
  readonly fatal: boolean;
}

interface DiagnosticPosition {
  readonly line: number;
  readonly column: number;
  readonly endLine: number;
  readonly endColumn: number;
}

interface FrontendSourceRepositorySnapshot {
  readonly trackedFiles: readonly string[];
  readonly carrierGitBlobs: Readonly<Record<string, string>>;
  readonly sourceStatus: readonly string[];
}

const boundaryFixtures: readonly BoundaryFixture[] = [
  {
    relativePath: "src/api/__boundary_fixture__.ts",
    carrierFile: "frontend/src/api/client.ts",
    source: 'import "../pages/FoundationPage";\n',
    expectedMessage: "The API layer must not depend on UI or app layers.",
  },
  {
    relativePath: "src/components/__boundary_fixture__.tsx",
    carrierFile: "frontend/src/components/SystemStatus.tsx",
    source: 'import "../pages/FoundationPage";\n',
    expectedMessage: "Components must not depend on pages.",
  },
  {
    relativePath: "src/app/__boundary_fixture__.tsx",
    carrierFile: "frontend/src/app/AppRouter.tsx",
    source: 'import "../test/setup";\n',
    expectedMessage: "Production source must not import test code.",
  },
  {
    relativePath: "src/api/__project_boundary_fixture__.ts",
    carrierFile: "frontend/src/api/client.ts",
    source: 'import "../features/projects/components/ProjectList";\n',
    expectedMessage: "The shared API layer must not depend on feature UI code.",
    expectedAdditionalArchitectureMessages: [
      "The API layer must not depend on UI or app layers.",
    ],
    expectedArchitectureCount: 2,
  },
  {
    relativePath: "src/features/projects/api/__boundary_fixture__.ts",
    carrierFile: "frontend/src/features/projects/api/client.ts",
    source: 'import React from "react";\nexport { React };\n',
    expectedMessage:
      "The Project API layer must stay independent from React and UI layers.",
  },
  {
    relativePath: "src/features/projects/hooks/__boundary_fixture__.ts",
    carrierFile: "frontend/src/features/projects/hooks/useProjectDetails.ts",
    source: 'import "../components/CreateProjectForm";\n',
    expectedMessage: "Project hooks must not depend on components or pages.",
  },
  {
    relativePath: "src/features/projects/components/__boundary_fixture__.tsx",
    carrierFile: "frontend/src/features/projects/components/ProjectDetails.tsx",
    source: 'void fetch("/api/v1/projects");\n',
    expectedMessage:
      "Project components must use hooks and the typed Project API client.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath: "src/features/projects/hooks/__storage_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/projects/hooks/useProjectDetails.ts",
    source: 'localStorage.setItem("project_etag", etag);\n',
    expectedMessage:
      "Project code must not persist security, cursor, ETag, or draft state.",
    expectedRule: "no-restricted-globals",
    expectedAdditionalRules: ["@typescript-eslint/no-unsafe-argument"],
  },
  {
    relativePath:
      "src/features/projects/hooks/__history_storage_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/projects/hooks/useProjectDetails.ts",
    source:
      'localStorage.setItem("project_revision_cursor", cursor);\nsessionStorage.setItem("project_revision_description", description);\n',
    expectedMessage:
      "Project code must not persist security, cursor, ETag, or draft state.",
    expectedRule: "no-restricted-globals",
    expectedArchitectureCount: 2,
    expectedAdditionalRules: ["@typescript-eslint/no-unsafe-argument"],
  },
  {
    relativePath:
      "src/features/projects/components/__cookie_boundary_fixture__.tsx",
    carrierFile: "frontend/src/features/projects/components/ProjectDetails.tsx",
    source: "const session = document.cookie;\nexport { session };\n",
    expectedMessage: "Project code must not read browser cookies.",
    expectedRule: "no-restricted-syntax",
  },
  {
    relativePath: "src/api/__story_bible_boundary_fixture__.ts",
    carrierFile: "frontend/src/api/client.ts",
    source: 'import "../features/story-bible/components/StoryBibleEditor";\n',
    expectedMessage: "The shared API layer must not depend on feature UI code.",
    expectedAdditionalArchitectureMessages: [
      "The API layer must not depend on UI or app layers.",
    ],
    expectedArchitectureCount: 2,
  },
  {
    relativePath: "src/features/story-bible/api/__react_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/story-bible/api/client.ts",
    source: 'import React from "react";\nexport { React };\n',
    expectedMessage:
      "The Story Bible API layer must stay independent from React, UI, and Project feature code.",
  },
  {
    relativePath:
      "src/features/story-bible/api/__project_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/story-bible/api/client.ts",
    source: 'import "../../projects/components/ProjectList";\n',
    expectedMessage:
      "The Story Bible API layer must stay independent from React, UI, and Project feature code.",
  },
  {
    relativePath:
      "src/features/story-bible/hooks/__component_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/story-bible/hooks/useStoryBible.ts",
    source: 'import "../components/StoryBibleEditor";\n',
    expectedMessage:
      "Story Bible hooks must not depend on components or pages.",
  },
  {
    relativePath:
      "src/features/story-bible/components/__fetch_boundary_fixture__.tsx",
    carrierFile:
      "frontend/src/features/story-bible/components/StoryBibleEditor.tsx",
    source: 'void fetch("/api/v1/story-bibles/example");\n',
    expectedMessage:
      "Story Bible components must use hooks and the typed Story Bible API client.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/story-bible/hooks/__storage_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/story-bible/hooks/useStoryBible.ts",
    source:
      'localStorage.setItem("story_bible_etag", etag);\nsessionStorage.setItem("story_bible_draft", draft);\n',
    expectedMessage:
      "Story Bible code must not persist security, ETag, or draft state.",
    expectedRule: "no-restricted-globals",
    expectedArchitectureCount: 2,
    expectedAdditionalRules: ["@typescript-eslint/no-unsafe-argument"],
  },
  {
    relativePath:
      "src/features/story-bible/components/__cookie_boundary_fixture__.tsx",
    carrierFile:
      "frontend/src/features/story-bible/components/StoryBibleEditor.tsx",
    source: "const session = document.cookie;\nexport { session };\n",
    expectedMessage: "Story Bible code must not read browser cookies.",
    expectedRule: "no-restricted-syntax",
  },
  {
    relativePath: "src/api/__character_boundary_fixture__.ts",
    carrierFile: "frontend/src/api/client.ts",
    source: 'import "../features/character/components/CharacterEditor";\n',
    expectedMessage: "The shared API layer must not depend on feature UI code.",
    expectedAdditionalArchitectureMessages: [
      "The API layer must not depend on UI or app layers.",
    ],
    expectedArchitectureCount: 2,
  },
  {
    relativePath: "src/features/character/api/__react_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/character/api/client.ts",
    source: 'import React from "react";\nexport { React };\n',
    expectedMessage:
      "The Character API layer must stay independent from React, UI, Project, and Story Bible feature code.",
  },
  {
    relativePath:
      "src/features/character/hooks/__component_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/character/hooks/useCharacterEditor.ts",
    source: 'import "../components/CharacterEditor";\n',
    expectedMessage: "Character hooks must not depend on components or pages.",
  },
  {
    relativePath:
      "src/features/character/components/__fetch_boundary_fixture__.tsx",
    carrierFile:
      "frontend/src/features/character/components/CharacterEditor.tsx",
    source: 'void fetch("/api/v1/characters/example");\n',
    expectedMessage:
      "Character components must use hooks and the typed Character API client.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/character/hooks/__storage_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/character/hooks/useCharacterEditor.ts",
    source:
      'localStorage.setItem("character_etag", etag);\nsessionStorage.setItem("character_profile", profile);\n',
    expectedMessage:
      "Character code must not persist profile, draft, cursor, ETag, or security state.",
    expectedRule: "no-restricted-globals",
    expectedArchitectureCount: 2,
    expectedAdditionalRules: ["@typescript-eslint/no-unsafe-argument"],
  },
  {
    relativePath:
      "src/features/character/components/__cookie_boundary_fixture__.tsx",
    carrierFile:
      "frontend/src/features/character/components/CharacterEditor.tsx",
    source: "const session = document.cookie;\nexport { session };\n",
    expectedMessage: "Character code must not read browser cookies.",
    expectedRule: "no-restricted-syntax",
  },
  {
    relativePath:
      "src/features/character/api/__history_ui_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/character/api/client.ts",
    source: 'import "../components/CharacterRevisionHistory";\n',
    expectedMessage:
      "The Character API layer must stay independent from React, UI, Project, and Story Bible feature code.",
  },
  {
    relativePath:
      "src/features/character/hooks/__history_page_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/character/hooks/useCharacterEditor.ts",
    source: 'import "../pages/CharacterRevisionHistoryPage";\n',
    expectedMessage: "Character hooks must not depend on components or pages.",
  },
  {
    relativePath:
      "src/features/character/components/__history_fetch_boundary_fixture__.tsx",
    carrierFile:
      "frontend/src/features/character/components/CharacterEditor.tsx",
    source: 'void fetch("/api/v1/characters/example/revisions");\n',
    expectedMessage:
      "Character components must use hooks and the typed Character API client.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/character/hooks/__history_storage_boundary_fixture__.ts",
    carrierFile: "frontend/src/features/character/hooks/useCharacterEditor.ts",
    source:
      'localStorage.setItem("character_revision_cursor", cursor);\nsessionStorage.setItem("character_revision_profile", profile);\n',
    expectedMessage:
      "Character code must not persist profile, draft, cursor, ETag, or security state.",
    expectedRule: "no-restricted-globals",
    expectedArchitectureCount: 2,
    expectedAdditionalRules: ["@typescript-eslint/no-unsafe-argument"],
  },
];

function presentControlledFixturePaths(): readonly string[] {
  return boundaryFixtures
    .filter((fixture) =>
      existsSync(path.join(frontendRoot, fixture.relativePath)),
    )
    .map((fixture) => fixture.relativePath);
}

function isFlatConfigArray(value: unknown): value is Linter.Config[] {
  return (
    Array.isArray(value) &&
    value.length === 23 &&
    value.every((entry: unknown) => typeof entry === "object" && entry !== null)
  );
}

function isLinterConfig(value: unknown): value is Linter.Config {
  return typeof value === "object" && value !== null;
}

async function loadProjectFlatConfig(): Promise<Linter.Config[]> {
  const configUrl = pathToFileURL(
    path.join(frontendRoot, "eslint.config.js"),
  ).href;
  const configModule: unknown = await import(configUrl);
  if (
    typeof configModule !== "object" ||
    configModule === null ||
    !("default" in configModule)
  ) {
    throw new Error("The project ESLint module must have a default export.");
  }
  const exportedConfig: unknown = configModule.default;
  if (!isFlatConfigArray(exportedConfig)) {
    throw new Error(
      "The project ESLint module must export 23 Flat Config entries.",
    );
  }
  return exportedConfig;
}

let projectFlatConfigLoads = 0;
const projectFlatConfig = await loadProjectFlatConfig();
projectFlatConfigLoads += 1;
let eslintInstances = 0;
const projectEslint = new ESLint({
  cwd: repositoryRoot,
  overrideConfigFile: "frontend/eslint.config.js",
});
eslintInstances += 1;
let calculateConfigForFileCalls = 0;
const representativeCarrier = path.join(
  repositoryRoot,
  boundaryFixtures[0].carrierFile,
);
calculateConfigForFileCalls += 1;
const calculatedRepresentativeConfig: unknown =
  await projectEslint.calculateConfigForFile(representativeCarrier);
if (!isLinterConfig(calculatedRepresentativeConfig)) {
  throw new Error("The representative effective config must be an object.");
}
const representativeConfig = calculatedRepresentativeConfig;

function frontendSourceRepositorySnapshot(): FrontendSourceRepositorySnapshot {
  const indexOutput = execFileSync(
    "git",
    ["ls-files", "--stage", "--", "frontend/src"],
    { cwd: repositoryRoot, encoding: "utf8" },
  ).trim();
  const trackedFiles: string[] = [];
  const indexBlobs = new Map<string, string>();
  for (const entry of indexOutput === "" ? [] : indexOutput.split(/\r?\n/u)) {
    const match = /^(?:\d+)\s+([0-9a-f]+)\s+\d\t(.+)$/u.exec(entry);
    if (match?.[1] === undefined || match[2] === undefined) {
      throw new Error(`Unexpected git ls-files entry: ${entry}`);
    }
    trackedFiles.push(match[2]);
    indexBlobs.set(match[2], match[1]);
  }
  const carriers = [
    ...new Set(boundaryFixtures.map((fixture) => fixture.carrierFile)),
  ];
  const carrierGitBlobs = Object.fromEntries(
    carriers.map((carrierFile) => {
      const blob = indexBlobs.get(carrierFile);
      if (blob === undefined) {
        throw new Error(`Carrier is not Git tracked: ${carrierFile}`);
      }
      return [carrierFile, blob];
    }),
  );
  const statusOutput = execFileSync(
    "git",
    ["status", "--short", "--", "frontend/src"],
    { cwd: repositoryRoot, encoding: "utf8" },
  ).trim();
  return {
    trackedFiles,
    carrierGitBlobs,
    sourceStatus: statusOutput === "" ? [] : statusOutput.split(/\r?\n/u),
  };
}

function carrierBlobSnapshot(): Readonly<Record<string, string>> {
  const carriers = new Set(
    boundaryFixtures.map((fixture) => fixture.carrierFile),
  );
  return Object.fromEntries(
    [...carriers].map((carrierFile) => [
      carrierFile,
      createHash("sha256")
        .update(readFileSync(path.join(repositoryRoot, carrierFile)))
        .digest("hex"),
    ]),
  );
}

const configurationFiles = [
  "frontend/eslint.config.js",
  "frontend/tsconfig.app.json",
  "frontend/tsconfig.e2e.json",
  "frontend/tsconfig.json",
  "frontend/tsconfig.node.json",
  "frontend/tsconfig.test.json",
] as const;

function configurationBlobSnapshot(): Readonly<Record<string, string>> {
  return Object.fromEntries(
    configurationFiles.map((configurationFile) => [
      configurationFile,
      createHash("sha256")
        .update(readFileSync(path.join(repositoryRoot, configurationFile)))
        .digest("hex"),
    ]),
  );
}

const architectureRuleIds = new Set([
  "no-restricted-imports",
  "no-restricted-globals",
  "no-restricted-syntax",
]);

function lintMessageKey(message: Linter.LintMessage): string {
  return [
    message.ruleId ?? "configuration",
    message.line,
    message.column,
    message.endLine ?? 0,
    message.endColumn ?? 0,
    message.message,
  ].join("|");
}

function sourceLineCount(source: string): number {
  if (source.length === 0) {
    return 0;
  }
  return source.split("\n").length - (source.endsWith("\n") ? 1 : 0);
}

function aggregateBoundaryFixtures(): readonly BoundaryFixtureGroup[] {
  const groups = new Map<
    string,
    {
      carrierFile: string;
      source: string;
      segments: BoundaryFixtureSegment[];
    }
  >();

  for (const [sampleIndex, fixture] of boundaryFixtures.entries()) {
    const group = groups.get(fixture.carrierFile) ?? {
      carrierFile: fixture.carrierFile,
      source: "",
      segments: [],
    };
    const marker = `// boundary-sample-${sampleIndex + 1}: ${fixture.relativePath}\n`;
    group.source += marker;
    const startLine = sourceLineCount(group.source) + 1;
    const source = fixture.source.endsWith("\n")
      ? fixture.source
      : `${fixture.source}\n`;
    group.source += source;
    group.segments.push({
      fixture,
      startLine,
      endLine: startLine + sourceLineCount(source) - 1,
    });
    groups.set(fixture.carrierFile, group);
  }

  return [...groups.values()];
}

const boundaryFixtureGroups = aggregateBoundaryFixtures();

function normalizeDiagnostic(
  message: Linter.LintMessage,
  lineOffset: number,
): NormalizedDiagnostic {
  return {
    ruleId: message.ruleId,
    severity: message.severity,
    message: message.message,
    line: message.line - lineOffset,
    column: message.column,
    endLine:
      message.endLine === undefined ? null : message.endLine - lineOffset,
    endColumn: message.endColumn ?? null,
    fatal: message.fatal === true,
  };
}

function normalizedDiagnosticKey(message: NormalizedDiagnostic): string {
  return [
    message.ruleId ?? "configuration",
    message.line,
    message.column,
    message.endLine ?? 0,
    message.endColumn ?? 0,
    message.message,
  ].join("|");
}

function tokenPositions(
  source: string,
  pattern: RegExp,
): readonly DiagnosticPosition[] {
  const positions: DiagnosticPosition[] = [];
  for (const [lineIndex, line] of source.split("\n").entries()) {
    for (const match of line.matchAll(pattern)) {
      if (match.index === undefined) {
        continue;
      }
      positions.push({
        line: lineIndex + 1,
        column: match.index + 1,
        endLine: lineIndex + 1,
        endColumn: match.index + 1 + match[0].length,
      });
    }
  }
  return positions;
}

function expectedArchitecturePositions(
  fixture: BoundaryFixture,
): readonly DiagnosticPosition[] {
  const ruleId = fixture.expectedRule ?? "no-restricted-imports";
  const expectedCount = fixture.expectedArchitectureCount ?? 1;
  if (ruleId === "no-restricted-imports") {
    const [importPosition] = tokenPositions(fixture.source, /^import.*;$/gmu);
    if (importPosition === undefined) {
      throw new Error(`No import position for ${fixture.relativePath}`);
    }
    return Array.from({ length: expectedCount }, () => importPosition);
  }
  if (ruleId === "no-restricted-globals") {
    const positions = tokenPositions(
      fixture.source,
      /\b(?:fetch|localStorage|sessionStorage)\b/gu,
    );
    if (positions.length !== expectedCount) {
      throw new Error(
        `Unexpected restricted-global count for ${fixture.relativePath}`,
      );
    }
    return positions;
  }
  if (ruleId === "no-restricted-syntax") {
    const positions = tokenPositions(fixture.source, /document\.cookie/gu);
    if (positions.length !== expectedCount) {
      throw new Error(
        `Unexpected restricted-syntax count for ${fixture.relativePath}`,
      );
    }
    return positions;
  }
  throw new Error(`Unsupported architecture rule: ${ruleId}`);
}

function expectedArchitectureDiagnostics(
  fixture: BoundaryFixture,
): readonly NormalizedDiagnostic[] {
  const ruleId = fixture.expectedRule ?? "no-restricted-imports";
  const positions = expectedArchitecturePositions(fixture);
  const messageFragments = [
    fixture.expectedMessage,
    ...(fixture.expectedAdditionalArchitectureMessages ?? []),
  ];
  let messages: readonly string[];

  if (ruleId === "no-restricted-imports") {
    const importSpecifier = /(?:from\s+)?["'](?<specifier>[^"']+)["']/u.exec(
      fixture.source,
    )?.groups?.specifier;
    if (importSpecifier === undefined) {
      throw new Error(`No import specifier for ${fixture.relativePath}`);
    }
    messages = messageFragments.map(
      (fragment) =>
        `'${importSpecifier}' import is restricted from being used by a pattern. ${fragment}`,
    );
  } else if (ruleId === "no-restricted-globals") {
    const globals = [
      ...fixture.source.matchAll(
        /\b(?<global>fetch|localStorage|sessionStorage)\b/gu,
      ),
    ].map((match) => match.groups?.global);
    if (
      globals.some((globalName) => globalName === undefined) ||
      globals.length !== positions.length
    ) {
      throw new Error(`No restricted global for ${fixture.relativePath}`);
    }
    messages = globals.map(
      (globalName) =>
        `Unexpected use of '${globalName}'. ${fixture.expectedMessage}`,
    );
  } else {
    messages = messageFragments;
  }

  if (messages.length !== positions.length) {
    throw new Error(`Unexpected diagnostic count for ${fixture.relativePath}`);
  }

  return positions
    .map((position, index) => ({
      ruleId,
      severity: 2,
      message: messages[index] ?? "",
      line: position.line,
      column: position.column,
      endLine: position.endLine,
      endColumn: position.endColumn,
      fatal: false,
    }))
    .sort((left, right) =>
      normalizedDiagnosticKey(left).localeCompare(
        normalizedDiagnosticKey(right),
      ),
    );
}

describe("frontend import boundaries", () => {
  beforeAll(() => {
    // These fixtures replace source in memory and add files during the session.
    // CI's immutable single-run Programs would instead lint stale disk contents.
    // Keep the production rules/config intact; only declare this harness's lifecycle.
    vi.stubEnv("TSESTREE_SINGLE_RUN", "false");
  });

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  it("rejects controlled illegal imports without polluting production source", () => {
    const configurationBlobsBefore = configurationBlobSnapshot();
    const repositoryBefore = frontendSourceRepositorySnapshot();
    const trackedFileSet = new Set(repositoryBefore.trackedFiles);
    const carrierBlobsBefore = carrierBlobSnapshot();
    let linterInstances = 0;
    const linter = new Linter({ cwd: repositoryRoot, configType: "flat" });
    linterInstances += 1;
    let verifyCalls = 0;
    const fixtureDiskWrites = 0;

    expect(boundaryFixtures).toHaveLength(27);
    expect(boundaryFixtureGroups).toHaveLength(12);
    expect(presentControlledFixturePaths()).toEqual([]);
    // Feature candidates may legitimately be present before this test; the
    // final snapshot assertion proves the controlled fixtures changed none of them.

    try {
      expect(Object.keys(representativeConfig)).not.toHaveLength(0);
      expect(
        representativeConfig.plugins?.["@typescript-eslint"],
      ).toBeDefined();
      expect(representativeConfig.languageOptions?.parser).toBeDefined();
      const parserOptions = representativeConfig.languageOptions?.parserOptions;
      expect(
        typeof parserOptions === "object" &&
          parserOptions !== null &&
          "project" in parserOptions,
      ).toBe(true);
      expect(
        representativeConfig.rules?.["no-restricted-imports"],
      ).toBeDefined();

      const observedSampleIds = new Set<string>();
      for (const group of boundaryFixtureGroups) {
        const carrierPath = path.join(repositoryRoot, group.carrierFile);
        const groupMessages = linter
          .verify(group.source, projectFlatConfig, { filename: carrierPath })
          .sort((left, right) =>
            lintMessageKey(left).localeCompare(lintMessageKey(right)),
          );
        verifyCalls += 1;
        const groupFatalOrConfigurationErrors = groupMessages.filter(
          (message) => message.fatal === true || message.ruleId === null,
        );
        expect(groupFatalOrConfigurationErrors).toEqual([]);
        let assignedMessageCount = 0;

        for (const segment of group.segments) {
          const { fixture } = segment;
          observedSampleIds.add(fixture.relativePath);
          const expectedCarrierDirectory = `frontend/${path.posix.dirname(
            fixture.relativePath,
          )}/`;
          expect(existsSync(carrierPath)).toBe(true);
          expect(trackedFileSet.has(fixture.carrierFile)).toBe(true);
          expect(path.extname(fixture.relativePath)).toBe(
            path.extname(fixture.carrierFile),
          );
          expect(fixture.carrierFile.startsWith(expectedCarrierDirectory)).toBe(
            true,
          );

          const messages = groupMessages
            .filter(
              (message) =>
                message.line >= segment.startLine &&
                message.line <= segment.endLine,
            )
            .map((message) =>
              normalizeDiagnostic(message, segment.startLine - 1),
            )
            .sort((left, right) =>
              normalizedDiagnosticKey(left).localeCompare(
                normalizedDiagnosticKey(right),
              ),
            );
          assignedMessageCount += messages.length;
          const fatalOrConfigurationErrors = messages.filter(
            (message) => message.fatal || message.ruleId === null,
          );
          const architectureMessages = messages.filter(
            (message) =>
              message.ruleId !== null &&
              architectureRuleIds.has(message.ruleId),
          );
          const additionalRuleIds = [
            ...new Set(
              messages
                .filter(
                  (message) =>
                    message.ruleId !== null &&
                    !architectureRuleIds.has(message.ruleId),
                )
                .map((message) => message.ruleId),
            ),
          ].sort();

          expect(fatalOrConfigurationErrors).toEqual([]);
          expect(architectureMessages).toEqual(
            expectedArchitectureDiagnostics(fixture),
          );
          expect(additionalRuleIds).toEqual(
            fixture.expectedAdditionalRules ?? [],
          );
        }

        expect(assignedMessageCount).toBe(groupMessages.length);
      }

      expect(observedSampleIds.size).toBe(27);
      expect(projectFlatConfigLoads).toBe(1);
      expect(eslintInstances).toBe(1);
      expect(calculateConfigForFileCalls).toBe(1);
      expect(linterInstances).toBe(1);
      expect(verifyCalls).toBe(12);
      expect(fixtureDiskWrites).toBe(0);
    } finally {
      expect(presentControlledFixturePaths()).toEqual([]);
      expect(frontendSourceRepositorySnapshot()).toEqual(repositoryBefore);
      expect(carrierBlobSnapshot()).toEqual(carrierBlobsBefore);
      expect(configurationBlobSnapshot()).toEqual(configurationBlobsBefore);
    }
  }, 15_000);

  it("accepts the controlled legal Project dependency direction", async () => {
    const fixturePath = path.join(
      frontendRoot,
      "src/features/projects/hooks/__legal_boundary_fixture__.ts",
    );
    try {
      await writeFile(
        fixturePath,
        'import type { ProjectDetailApiClient } from "../api/client";\nexport type LegalClient = ProjectDetailApiClient;\n',
        { encoding: "utf8", flag: "wx" },
      );
      const eslint = new ESLint({
        cwd: repositoryRoot,
        overrideConfigFile: "frontend/eslint.config.js",
      });
      const [result] = await eslint.lintFiles([fixturePath]);
      expect(result?.messages).toEqual([]);
      expect(result?.errorCount).toBe(0);
    } finally {
      try {
        await unlink(fixturePath);
      } catch (error) {
        if (
          typeof error !== "object" ||
          error === null ||
          !("code" in error) ||
          error.code !== "ENOENT"
        ) {
          throw error;
        }
      }
    }
  }, 15_000);

  it("accepts the controlled legal Story Bible dependency direction", async () => {
    const fixturePath = path.join(
      frontendRoot,
      "src/features/story-bible/hooks/__legal_boundary_fixture__.ts",
    );
    try {
      await writeFile(
        fixturePath,
        'import type { StoryBibleApiClient } from "../api/client";\nexport type LegalClient = StoryBibleApiClient;\n',
        { encoding: "utf8", flag: "wx" },
      );
      const eslint = new ESLint({
        cwd: repositoryRoot,
        overrideConfigFile: "frontend/eslint.config.js",
      });
      const [result] = await eslint.lintFiles([fixturePath]);
      expect(result?.messages).toEqual([]);
      expect(result?.errorCount).toBe(0);
    } finally {
      try {
        await unlink(fixturePath);
      } catch (error) {
        if (
          typeof error !== "object" ||
          error === null ||
          !("code" in error) ||
          error.code !== "ENOENT"
        ) {
          throw error;
        }
      }
    }
  }, 15_000);
});
