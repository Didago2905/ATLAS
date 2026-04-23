import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import BeerDetail from "./pages/BeerDetail";
import Home from "./pages/Home";
import AdminBeers from "./pages/AdminBeers";
import AdminLogin from "./pages/AdminLogin";
import AdminLayout from "./layout/AdminLayout";
import AdminParser from "./pages/AdminParser";
import Museum from "./pages/Museum";
import AdminMuseum from "./pages/AdminMuseum";

// 🔒 Protección de rutas
function ProtectedRoute({ children }) {
  const token = localStorage.getItem("token");

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

// 🔐 Wrapper para login con navegación limpia
function LoginWrapper() {
  const navigate = useNavigate();

  return (
    <AdminLogin
      onLogin={() => {
        navigate("/admin/beers");
      }}
    />
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>

        {/* 🟢 Público */}
        <Route path="/" element={<Home />} />
        <Route path="/beer/:id" element={<BeerDetail />} />
        <Route path="/museum" element={<Museum />} />

        {/* 🔐 Login */}
        <Route path="/login" element={<LoginWrapper />} />

        {/* 🔒 Admin */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute>
              <AdminLayout />
            </ProtectedRoute>
          }
        >

          {/* 🔥 Default */}
          <Route index element={<Navigate to="beers" replace />} />

          <Route path="beers" element={<AdminBeers />} />
          <Route path="parser" element={<AdminParser />} />

          <Route
            path="stats"
            element={
              <div style={{ width: "100%" }}>
                <h2>Stats próximamente</h2>
              </div>
            }
          />

          {/* 🔥 NUEVO — MUSEUM */}
          <Route path="museum" element={<AdminMuseum />} />

        </Route>

      </Routes>
    </BrowserRouter>
  );
}