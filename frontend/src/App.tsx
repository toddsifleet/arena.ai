import type { Component } from "solid-js";
import { Router, Route } from "@solidjs/router";
import { ClientProvider } from "./context/ClientContext";
import LobbyPage from "./pages/LobbyPage";
import RoomPage from "./pages/RoomPage";
import DashboardPage from "./pages/DashboardPage";

const App: Component = () => (
  <ClientProvider>
    <Router>
      <Route path="/" component={LobbyPage} />
      <Route path="/room/:id" component={RoomPage} />
      <Route path="/dashboard" component={DashboardPage} />
    </Router>
  </ClientProvider>
);

export default App;
