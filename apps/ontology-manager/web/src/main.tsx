import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { AgentPage } from "./pages/AgentPage";
import { ExplorePage } from "./pages/ExplorePage";
import {
  ActionTypesPage,
  Discover,
  LinkTypesPage,
  ObjectTypesList,
  ObjectTypeView,
  OntologyGraph,
  OntologyManager,
} from "./pages/OntologyManager";
import { WorkflowsPage } from "./pages/WorkflowsPage";
import { ThemeProvider } from "./state/theme";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/om.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60_000, refetchOnWindowFocus: false, retry: 1 } },
});

const router = createBrowserRouter([
  {
    element: (
      <>
        <div className="backdrop" aria-hidden><span /><span /><span /></div>
        <div className="om-app"><OntologyManager /></div>
      </>
    ),
    children: [
      { index: true, element: <Discover /> },
      { path: "object-types", element: <ObjectTypesList /> },
      { path: "object-types/:name", element: <ObjectTypeView /> },
      { path: "object-types/:name/:tab", element: <ObjectTypeView /> },
      { path: "link-types", element: <LinkTypesPage /> },
      { path: "action-types", element: <ActionTypesPage /> },
      { path: "graph", element: <OntologyGraph /> },
      { path: "explore", element: <ExplorePage /> },
      { path: "workflows", element: <WorkflowsPage /> },
      { path: "agent", element: <AgentPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
