import { Link, Route, Routes } from "react-router-dom";

import ScanPage from "./pages/ScanPage";
import ScansPage from "./pages/ScansPage";

export default function App() {
  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-6 px-6 py-6">
      <Link to="/" className="text-muted-foreground hover:text-foreground w-fit text-xs">
        Mini Gauntlet
      </Link>
      <main>
        <Routes>
          <Route path="/" element={<ScansPage />} />
          <Route path="/scans/:id" element={<ScanPage />} />
          <Route path="*" element={<p className="text-muted-foreground">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
