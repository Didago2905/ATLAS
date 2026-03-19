import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";

import Home from "./pages/Home";
import AdminBeers from "./pages/AdminBeers";
import AdminLogin from "./pages/AdminLogin";
import AdminLayout from "./layout/AdminLayout";
import AdminParser from "./pages/AdminParser";

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
        navigate("/admin/beers"); // 🔥 navegación correcta
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

          {/* 🔥 Default route */}
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

        </Route>

      </Routes>
    </BrowserRouter>
  );
}