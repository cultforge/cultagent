import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { ServerLayout } from "./layouts/ServerLayout";
import { AdminPage } from "./pages/AdminPage";
import { BackupsPage } from "./pages/BackupsPage";
import { BuildsPage } from "./pages/BuildsPage";
import { CloudPage } from "./pages/CloudPage";
import { ConfigPage } from "./pages/ConfigPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FilesPage } from "./pages/FilesPage";
import { MetricsPage } from "./pages/MetricsPage";
import { ModsPage } from "./pages/ModsPage";
import { NetworkPage } from "./pages/NetworkPage";
import { NewServerPage } from "./pages/NewServerPage";
import { ProfilesPage } from "./pages/ProfilesPage";
import { ServerOverviewPage } from "./pages/ServerOverviewPage";
import { ServersPage } from "./pages/ServersPage";
import { SystemPage } from "./pages/SystemPage";
import { TerminalPage } from "./pages/TerminalPage";
import { TunerPage } from "./pages/TunerPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="servers/new" element={<NewServerPage />} />
        <Route path="servers/:serverId" element={<ServerLayout />}>
          <Route index element={<ServerOverviewPage />} />
          <Route path="console" element={<TerminalPage />} />
          <Route path="files" element={<FilesPage />} />
          <Route path="config" element={<ConfigPage />} />
          <Route path="tuner" element={<TunerPage />} />
          <Route path="backups" element={<BackupsPage />} />
          <Route path="mods" element={<ModsPage />} />
          <Route path="metrics" element={<MetricsPage />} />
          <Route path="admin" element={<AdminPage />} />
        </Route>
        <Route path="network" element={<NetworkPage />} />
        <Route path="builds" element={<BuildsPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="cloud" element={<CloudPage />} />
        <Route path="profiles" element={<ProfilesPage />} />
        <Route path="*" element={<Navigate to="dashboard" replace />} />
      </Route>
    </Routes>
  );
}
