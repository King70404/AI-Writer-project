import { createE2EConfig } from "./playwright.shared";

export default createE2EConfig({
  defaultBaseURL: "http://127.0.0.1:14173",
  mode: "development",
});
