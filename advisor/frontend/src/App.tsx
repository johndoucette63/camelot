import { Link, Route, Routes, useLocation } from "react-router-dom";
import Home from "./pages/Home";
import { Devices } from "./pages/Devices";
import { Events } from "./pages/Events";

function Nav() {
  const location = useLocation();
  const linkClass = (path: string) =>
    `px-3 py-2 rounded text-sm font-medium ${
      location.pathname === path
        ? "bg-blue-100 text-blue-700"
        : "text-gray-600 hover:bg-gray-100"
    }`;
  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-2">
      <span className="font-bold text-gray-800 mr-4">Network Advisor</span>
      <Link to="/" className={linkClass("/")}>Home</Link>
      <Link to="/devices" className={linkClass("/devices")}>Devices</Link>
      <Link to="/events" className={linkClass("/events")}>Events</Link>
    </nav>
  );
}

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Nav />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/events" element={<Events />} />
      </Routes>
    </div>
  );
}

export default App;
