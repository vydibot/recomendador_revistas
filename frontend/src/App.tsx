import { Navigate, Route, Routes } from "react-router";
import Layout from "./components/Layout";
import CatalogPage from "./pages/CatalogPage";
import RecommenderPage from "./pages/RecommenderPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/catalogo" replace />} />
        <Route path="catalogo" element={<CatalogPage />} />
        <Route path="recomendador" element={<RecommenderPage />} />
        <Route path="*" element={<Navigate to="/catalogo" replace />} />
      </Route>
    </Routes>
  );
}
