import { Navigate, useSearchParams } from "react-router-dom";
import { useApp } from "@/state/AppContext";
import HomePage from "@/components/home/HomePage";

export default function Index() {
  const { state } = useApp();
  const [searchParams] = useSearchParams();
  const blueprintId = searchParams.get("blueprint_id");
  
  const ready = (state.uploadStage === "complete" && !!state.file && !!state.blueprintId) || !!blueprintId;

  if (ready) {
    return <Navigate to={`/workspace${blueprintId ? `?blueprint_id=${blueprintId}` : ""}`} replace />;
  }

  return <HomePage />;
}

