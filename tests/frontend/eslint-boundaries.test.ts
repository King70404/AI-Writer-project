import { writeFile, unlink } from "node:fs/promises";
import path from "node:path";

import { ESLint } from "eslint";
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
];

describe("frontend import boundaries", () => {
  it("rejects controlled illegal imports without polluting production source", async () => {
    const fixturePaths = boundaryFixtures.map((fixture) =>
      path.join(frontendRoot, fixture.relativePath),
    );

    try {
      await Promise.all(
        boundaryFixtures.map((fixture, index) =>
          writeFile(fixturePaths[index], fixture.source, {
            encoding: "utf8",
            flag: "wx",
          }),
        ),
      );

      const eslint = new ESLint({
        cwd: repositoryRoot,
        overrideConfigFile: "frontend/eslint.config.js",
      });
      const results = await eslint.lintFiles(fixturePaths);

      expect(results).toHaveLength(boundaryFixtures.length);
      for (const [index, result] of results.entries()) {
        expect(result.errorCount).toBeGreaterThan(0);
        const boundaryViolation = result.messages.find(
          (message) =>
            message.ruleId ===
              (boundaryFixtures[index].expectedRule ??
                "no-restricted-imports") &&
            message.message.includes(boundaryFixtures[index].expectedMessage),
        );
        expect(boundaryViolation).toBeDefined();
      }
    } finally {
      await Promise.all(
        fixturePaths.map(async (fixturePath) => {
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
        }),
      );
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
