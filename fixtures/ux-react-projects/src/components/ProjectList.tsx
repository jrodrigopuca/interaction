import "./ProjectList.css";

export type Project = { id: string; name: string; updatedAt: string };

export function ProjectList({ projects }: { projects: Project[] }) {
  return (
    <ul className="project-list">
      {projects.map((p) => (
        <li key={p.id} className="project-list__row">
          <span className="project-list__name">{p.name}</span>
          <time className="project-list__date">{p.updatedAt}</time>
        </li>
      ))}
    </ul>
  );
}
