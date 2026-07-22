import js from "@eslint/js";
import vitest from "@vitest/eslint-plugin";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

const typedFiles = [
  "frontend/src/**/*.{ts,tsx}",
  "frontend/tests/**/*.{ts,tsx}",
  "tests/frontend/**/*.{ts,tsx}",
  "tests/e2e/**/*.{ts,tsx}",
  "frontend/*.ts",
];
const sourceFiles = ["frontend/src/**/*.{ts,tsx}"];
const testImportPattern = {
  group: ["**/test/**", "**/tests/**"],
  message: "Production source must not import test code.",
};

function restrictedImports(...patterns) {
  return [
    "error",
    {
      patterns: [testImportPattern, ...patterns],
    },
  ];
}

const typedRecommended = tseslint.configs.recommendedTypeChecked.map(
  (configuration) => ({
    ...configuration,
    files: typedFiles,
  }),
);

export default [
  {
    ignores: [
      "frontend/node_modules/**",
      "frontend/dist/**",
      "frontend/coverage/**",
      "frontend/playwright-report/**",
      "frontend/playwright-results/**",
      "frontend/.vite/**",
      "**/*.tsbuildinfo",
    ],
    linterOptions: {
      reportUnusedDisableDirectives: "error",
    },
  },
  {
    ...js.configs.recommended,
    files: ["frontend/*.js"],
    languageOptions: {
      globals: globals.node,
    },
  },
  ...typedRecommended,
  {
    files: typedFiles,
    languageOptions: {
      parserOptions: {
        project: [
          "./tsconfig.app.json",
          "./tsconfig.test.json",
          "./tsconfig.node.json",
          "./tsconfig.e2e.json",
        ],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-empty-function": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
        },
      ],
    },
  },
  {
    files: sourceFiles,
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      "no-restricted-imports": restrictedImports(),
    },
  },
  {
    files: ["frontend/src/api/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictedImports(
        {
          group: ["**/components/**", "**/pages/**", "**/app/**"],
          message: "The API layer must not depend on UI or app layers.",
        },
        {
          group: ["**/features/projects/**"],
          message: "The shared API layer must not depend on Project UI code.",
        },
      ),
    },
  },
  {
    files: ["frontend/src/features/projects/api/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictedImports({
        group: [
          "react",
          "react/**",
          "**/components/**",
          "**/hooks/**",
          "**/pages/**",
        ],
        message:
          "The Project API layer must stay independent from React and UI layers.",
      }),
    },
  },
  {
    files: ["frontend/src/features/projects/hooks/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictedImports({
        group: ["**/components/**", "**/pages/**"],
        message: "Project hooks must not depend on components or pages.",
      }),
    },
  },
  {
    files: ["frontend/src/features/projects/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-globals": [
        "error",
        {
          name: "fetch",
          message:
            "Project components must use hooks and the typed Project API client.",
        },
        {
          name: "localStorage",
          message:
            "Project code must not persist security, cursor, ETag, or draft state.",
        },
        {
          name: "sessionStorage",
          message:
            "Project code must not persist security, cursor, ETag, or draft state.",
        },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "MemberExpression[object.name='document'][property.name='cookie']",
          message: "Project code must not read browser cookies.",
        },
      ],
    },
  },
  {
    files: ["frontend/src/components/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictedImports({
        group: ["**/pages/**"],
        message: "Components must not depend on pages.",
      }),
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "AssignmentExpression[left.object.name='window'][left.property.name='location']",
          message: "Use the client router for navigation.",
        },
        {
          selector:
            "AssignmentExpression[left.object.object.name='window'][left.object.property.name='location']",
          message: "Use the client router for navigation.",
        },
        {
          selector:
            "CallExpression[callee.object.object.name='window'][callee.object.property.name='location'][callee.property.name=/^(assign|replace)$/]",
          message: "Use the client router for navigation.",
        },
      ],
    },
  },
  {
    ...reactHooks.configs.flat.recommended,
    files: sourceFiles,
  },
  {
    ...jsxA11y.flatConfigs.recommended,
    files: ["frontend/src/**/*.tsx"],
    languageOptions: {
      ...jsxA11y.flatConfigs.recommended.languageOptions,
      globals: globals.browser,
    },
  },
  {
    ...reactRefresh.configs.vite,
    files: ["frontend/src/**/*.tsx"],
  },
  {
    ...vitest.configs.recommended,
    files: ["tests/frontend/**/*.{ts,tsx}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
        ...vitest.environments.env.globals,
      },
    },
  },
  {
    files: [
      "tests/e2e/**/*.{ts,tsx}",
      "frontend/tests/**/*.{ts,tsx}",
      "frontend/playwright*.ts",
    ],
    languageOptions: {
      globals: globals.node,
    },
  },
];
