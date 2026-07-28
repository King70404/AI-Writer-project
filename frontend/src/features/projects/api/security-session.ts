import {
  createSecuritySessionManager,
  securitySession,
  type SecurityProof,
  type SecuritySessionManager,
} from "../../../api/security-session";

export type ProjectSecurityProof = SecurityProof;
export type ProjectSecuritySessionManager = SecuritySessionManager;
export const createProjectSecuritySessionManager = createSecuritySessionManager;
export const projectSecuritySession = securitySession;
