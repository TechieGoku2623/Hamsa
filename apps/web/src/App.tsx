import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useSession } from "./session";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";
import StorePage from "./pages/StorePage";
import DashboardPage from "./pages/DashboardPage";

function RequireAuth({ children, allowGuest = false }: { children: React.ReactElement; allowGuest?: boolean }) {
  const { user, ready } = useSession();
  const loc = useLocation();
  if (!ready) return <div className="splash"><Logo /></div>;
  if (!user || (user.is_guest && !allowGuest)) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname)}`} replace />;
  return children;
}

export function Logo({ small = false }: { small?: boolean }) {
  return (
    <span className={small ? "logo small" : "logo"}>
      <img src="/favicon.svg" alt="" />
      <span>Hamsa</span>
    </span>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/b/:handle" element={<StorePage />} />
      <Route path="/business" element={<RequireAuth><DashboardPage /></RequireAuth>} />
      <Route path="/c/:id" element={<RequireAuth allowGuest><HomePage /></RequireAuth>} />
      <Route path="/" element={<RequireAuth allowGuest><HomePage /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
