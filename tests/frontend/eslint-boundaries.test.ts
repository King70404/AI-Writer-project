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
            message.ruleId === "no-restricted-imports" &&
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
});
