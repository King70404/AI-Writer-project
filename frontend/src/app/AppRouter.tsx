import { Route, Routes } from "react-router";

import {
  ProjectDetailsPage,
  ProjectRevisionHistoryPage,
} from "../features/projects";
import { NotFoundPage } from "../pages/NotFoundPage";
import {
  StoryBiblePage,
  StoryBibleRevisionHistoryPage,
} from "../features/story-bible";
import {
  CharacterEditorPage,
  CharacterListPage,
  CharacterRevisionHistoryPage,
} from "../features/character";
import {
  ChapterWritingPage,
  NovelStructurePage,
} from "../features/novel-structure";
import { BackupsPage } from "../features/author-backup";
import { AuthorHomePage } from "../features/workbench/pages/AuthorHomePage";
import { BookshelfPage } from "../features/workbench/pages/BookshelfPage";
import { AppShell } from "./AppShell";

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<AuthorHomePage />} />
        <Route path="projects" element={<BookshelfPage />} />
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
        <Route
          path="projects/:projectId/characters/:characterId/history"
          element={<CharacterRevisionHistoryPage />}
        />
        <Route
          path="projects/:projectId/structure"
          element={<NovelStructurePage />}
        />
        <Route
          path="projects/:projectId/chapters/:chapterId/write"
          element={<ChapterWritingPage />}
        />
        <Route path="backups" element={<BackupsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
