import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import "./index.css";
import Root, { ErrorBoundary } from "./routes/root";
import Index from "./routes/index";
import UploadExperience from "./components/upload/UploadExperience";
import Workspace from "./components/workspace/Workspace";
import { AppProvider } from "./state/AppContext";
import { DataScopeProvider } from "./state/DataScopeContext";
import { SheetContextProvider } from "./state/SheetContextProvider";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Root />,
    errorElement: <ErrorBoundary />,
    children: [
      { index: true, element: <Index /> },
      { path: "upload", element: <UploadExperience /> },
      { path: "workspace", element: <Workspace /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProvider>
      <DataScopeProvider>
        <SheetContextProvider>
          <RouterProvider router={router} />
        </SheetContextProvider>
      </DataScopeProvider>
    </AppProvider>
  </StrictMode>
);

