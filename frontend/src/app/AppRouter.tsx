import { Route, Routes } from "react-router";

import {
  ProjectDetailsPage,
  ProjectRevisionHistoryPage,
  ProjectsPage,
} from "../features/projects";
import { FoundationPage } from "../pages/FoundationPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import {
  StoryBiblePage,
  StoryBibleRevisionHistoryPage,
} from "../features/story-bible";
import { CharacterEditorPage, CharacterListPage } from "../features/character";
import { AppShell } from "./AppShell";

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<FoundationPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectDetailsPage />} />
        <Route
          path="projects/:projectId/history"
          element={<ProjectRevisionHistoryPage />}
        />
        <Route
          path="projects/:projectId/story-bible"
          element={<StoryBiblePage />}
        />
        <Route
          path="projects/:projectId/story-bible/history"
          element={<StoryBibleRevisionHistoryPage />}
        />
        <Route
          path="projects/:projectId/characters"
          element={<CharacterListPage />}
        />
        <Route
          path="projects/:projectId/characters/:characterId"
          element={<CharacterEditorPage />}
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
