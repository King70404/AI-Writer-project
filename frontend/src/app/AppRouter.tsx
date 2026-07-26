import { Route, Routes } from "react-router";

import {
  ProjectDetailsPage,
  ProjectRevisionHistoryPage,
  ProjectsPage,
} from "../features/projects";
import { FoundationPage } from "../pages/FoundationPage";
import { NotFoundPage } from "../pages/NotFoundPage";
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
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
