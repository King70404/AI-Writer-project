import { writeFile, unlink } from "node:fs/promises";
import path from "node:path";

import { ESLint, Linter } from "eslint";
import { describe, expect, it } from "vitest";

const repositoryRoot = path.resolve(process.cwd(), "..");
const frontendRoot = path.join(repositoryRoot, "frontend");

interface BoundaryFixture {
  readonly relativePath: string;
  readonly source: string;
  readonly expectedMessage: string;
  readonly expectedRule?: string;
}

const boundaryFixtures: readonly BoundaryFixture[] = [
  {
    relativePath: "src/api/__boundary_fixture__.ts",
    source: 'import "../pages/FoundationPage";\n',
    expectedMessage: "The API layer must not depend on UI or app layers.",
  },
  {
    relativePath: "src/components/__boundary_fixture__.ts",
    source: 'import "../pages/FoundationPage";\n',
    expectedMessage: "Components must not depend on pages.",
  },
  {
    relativePath: "src/app/__boundary_fixture__.ts",
    source: 'import "../test/setup";\n',
    expectedMessage: "Production source must not import test code.",
  },
  {
    relativePath: "src/api/__project_boundary_fixture__.ts",
    source: 'import "../features/projects/components/ProjectList";\n',
    expectedMessage: "The shared API layer must not depend on feature UI code.",
  },
  {
    relativePath: "src/features/projects/api/__boundary_fixture__.ts",
    source: 'import React from "react";\nexport { React };\n',
    expectedMessage:
      "The Project API layer must stay independent from React and UI layers.",
  },
  {
    relativePath: "src/features/projects/hooks/__boundary_fixture__.ts",
    source: 'import "../components/CreateProjectForm";\n',
    expectedMessage: "Project hooks must not depend on components or pages.",
  },
  {
    relativePath: "src/features/projects/components/__boundary_fixture__.ts",
    source: 'void fetch("/api/v1/projects");\n',
    expectedMessage:
      "Project components must use hooks and the typed Project API client.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath: "src/features/projects/hooks/__storage_boundary_fixture__.ts",
    source: 'localStorage.setItem("project_etag", etag);\n',
    expectedMessage:
      "Project code must not persist security, cursor, ETag, or draft state.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/projects/hooks/__history_storage_boundary_fixture__.ts",
    source:
      'localStorage.setItem("project_revision_cursor", cursor);\nsessionStorage.setItem("project_revision_description", description);\n',
    expectedMessage:
      "Project code must not persist security, cursor, ETag, or draft state.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/projects/components/__cookie_boundary_fixture__.ts",
    source: "const session = document.cookie;\nexport { session };\n",
    expectedMessage: "Project code must not read browser cookies.",
    expectedRule: "no-restricted-syntax",
  },
  {
    relativePath: "src/api/__story_bible_boundary_fixture__.ts",
    source: 'import "../features/story-bible/components/StoryBibleEditor";\n',
    expectedMessage: "The shared API layer must not depend on feature UI code.",
  },
  {
    relativePath: "src/features/story-bible/api/__react_boundary_fixture__.ts",
    source: 'import React from "react";\nexport { React };\n',
    expectedMessage:
      "The Story Bible API layer must stay independent from React, UI, and Project feature code.",
  },
  {
    relativePath:
      "src/features/story-bible/api/__project_boundary_fixture__.ts",
    source: 'import "../../projects/components/ProjectList";\n',
    expectedMessage:
      "The Story Bible API layer must stay independent from React, UI, and Project feature code.",
  },
  {
    relativePath:
      "src/features/story-bible/hooks/__component_boundary_fixture__.ts",
    source: 'import "../components/StoryBibleEditor";\n',
    expectedMessage:
      "Story Bible hooks must not depend on components or pages.",
  },
  {
    relativePath:
      "src/features/story-bible/components/__fetch_boundary_fixture__.ts",
    source: 'void fetch("/api/v1/story-bibles/example");\n',
    expectedMessage:
      "Story Bible components must use hooks and the typed Story Bible API client.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/story-bible/hooks/__storage_boundary_fixture__.ts",
    source:
      'localStorage.setItem("story_bible_etag", etag);\nsessionStorage.setItem("story_bible_draft", draft);\n',
    expectedMessage:
      "Story Bible code must not persist security, ETag, or draft state.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/story-bible/components/__cookie_boundary_fixture__.ts",
    source: "const session = document.cookie;\nexport { session };\n",
    expectedMessage: "Story Bible code must not read browser cookies.",
    expectedRule: "no-restricted-syntax",
  },
  {
    relativePath: "src/api/__character_boundary_fixture__.ts",
    source: 'import "../features/character/components/CharacterEditor";\n',
    expectedMessage: "The shared API layer must not depend on feature UI code.",
  },
  {
    relativePath: "src/features/character/api/__react_boundary_fixture__.ts",
    source: 'import React from "react";\nexport { React };\n',
    expectedMessage:
      "The Character API layer must stay independent from React, UI, Project, and Story Bible feature code.",
  },
  {
    relativePath:
      "src/features/character/hooks/__component_boundary_fixture__.ts",
    source: 'import "../components/CharacterEditor";\n',
    expectedMessage: "Character hooks must not depend on components or pages.",
  },
  {
    relativePath:
      "src/features/character/components/__fetch_boundary_fixture__.ts",
    source: 'void fetch("/api/v1/characters/example");\n',
    expectedMessage:
      "Character components must use hooks and the typed Character API client.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/character/hooks/__storage_boundary_fixture__.ts",
    source:
      'localStorage.setItem("character_etag", etag);\nsessionStorage.setItem("character_profile", profile);\n',
    expectedMessage:
      "Character code must not persist profile, draft, cursor, ETag, or security state.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/character/components/__cookie_boundary_fixture__.ts",
    source: "const session = document.cookie;\nexport { session };\n",
    expectedMessage: "Character code must not read browser cookies.",
    expectedRule: "no-restricted-syntax",
  },
  {
    relativePath:
      "src/features/character/api/__history_ui_boundary_fixture__.ts",
    source: 'import "../components/CharacterRevisionHistory";\n',
    expectedMessage:
      "The Character API layer must stay independent from React, UI, Project, and Story Bible feature code.",
  },
  {
    relativePath:
      "src/features/character/hooks/__history_page_boundary_fixture__.ts",
    source: 'import "../pages/CharacterRevisionHistoryPage";\n',
    expectedMessage: "Character hooks must not depend on components or pages.",
  },
  {
    relativePath:
      "src/features/character/components/__history_fetch_boundary_fixture__.ts",
    source: 'void fetch("/api/v1/characters/example/revisions");\n',
    expectedMessage:
      "Character components must use hooks and the typed Character API client.",
    expectedRule: "no-restricted-globals",
  },
  {
    relativePath:
      "src/features/character/hooks/__history_storage_boundary_fixture__.ts",
    source:
      'localStorage.setItem("character_revision_cursor", cursor);\nsessionStorage.setItem("character_revision_profile", profile);\n',
    expectedMessage:
      "Character code must not persist profile, draft, cursor, ETag, or security state.",
    expectedRule: "no-restricted-globals",
  },
];

describe("frontend import boundaries", () => {
  it("rejects controlled illegal imports without polluting production source", async () => {
    const eslint = new ESLint({
      cwd: repositoryRoot,
      overrideConfigFile: "frontend/eslint.config.js",
    });
    const linter = new Linter({ cwd: repositoryRoot, configType: "flat" });

    for (const fixture of boundaryFixtures) {
      const fixturePath = path.join(frontendRoot, fixture.relativePath);
      const ruleId = fixture.expectedRule ?? "no-restricted-imports";
      const configured = (await eslint.calculateConfigForFile(
        fixturePath,
      )) as Linter.Config;
      const ruleConfiguration = configured.rules?.[ruleId];
      expect(
        ruleConfiguration,
        `${fixture.relativePath} must enable ${ruleId}`,
      ).toBeDefined();
      if (ruleConfiguration === undefined) {
        continue;
      }

      const messages = linter.verify(
        fixture.source,
        {
          files: ["**/*.ts"],
          languageOptions: {
            ecmaVersion: "latest",
            sourceType: "module",
          },
          rules: {
            [ruleId]: ruleConfiguration,
          },
        },
        { filename: fixture.relativePath },
      );
      const boundaryViolation = messages.find(
        (message) =>
          message.ruleId === ruleId &&
          message.message.includes(fixture.expectedMessage),
      );
      expect(
        boundaryViolation,
        `${fixture.relativePath} must be rejected by ${ruleId}; observed rules: ${
          messages
            .map((message) => message.ruleId ?? "configuration")
            .join(", ") || "none"
        }; diagnostics: ${messages.map((message) => message.message).join(" | ")}`,
      ).toBeDefined();
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
