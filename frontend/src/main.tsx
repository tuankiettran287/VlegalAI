import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";
import "./redesign.css";
import "./professional.css";
import "./landing.css";
import "./onboarding.css";
import "./vlegal-ui.css";

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
