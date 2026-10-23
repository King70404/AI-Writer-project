import { projectApiClient, type ProjectApiClient } from "../api/client";
import { CreateProjectForm } from "../components/CreateProjectForm";
import {
  ProjectList,
  type ContinueWritingPath,
} from "../components/ProjectList";
import { ProjectPageHeader } from "../components/ProjectPageHeader";
import { useProjectList } from "../hooks/useProjectList";

interface ProjectsPageProps {
  readonly client?: ProjectApiClient;
  /** 由应用层提供的本机“继续写作”定位；项目模块本身不读写浏览器存储。 */
  readonly continueWritingPath?: ContinueWritingPath;
}

export function ProjectsPage({
  client = projectApiClient,
  continueWritingPath,
}: ProjectsPageProps) {
  const projectList = useProjectList(client);

  return (
    <section
      className="projects-page"
      data-feature-id="PRJ-005"
      aria-labelledby="projects-title"
    >
      <ProjectPageHeader />
      <CreateProjectForm client={client} reloadProjects={projectList.reload} />
      <section
        className="projects-page__list"
        aria-labelledby="project-list-title"
      >
        <div className="projects-page__list-heading">
          <div>
            <p className="section-kicker">你的创作</p>
            <h3 id="project-list-title">我的小说</h3>
          </div>
          <button type="button" onClick={() => void projectList.reload()}>
            刷新
          </button>
        </div>
        <ProjectList
          controller={projectList}
          continueWritingPath={continueWritingPath}
        />
      </section>
    </section>
  );
}
