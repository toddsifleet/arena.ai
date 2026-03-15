import { fireEvent, render, screen } from "@solidjs/testing-library";
import { describe, expect, it, vi } from "vitest";
import LobbyPage from "./LobbyPage";

const navigateMock = vi.fn();
const createRoomMock = vi.fn();

vi.mock("@solidjs/router", async () => {
  const mod = await vi.importActual("@solidjs/router");
  return {
    ...mod,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../rtc", () => ({
  createRoom: () => createRoomMock(),
}));

describe("LobbyPage", () => {
  it("shows validation error for malformed room IDs", async () => {
    render(() => <LobbyPage />);

    const input = screen.getByPlaceholderText("Room ID");
    const joinButton = screen.getByRole("button", { name: "Join" });

    await fireEvent.input(input, { target: { value: "abc" } });
    await fireEvent.click(joinButton);

    expect(screen.getByText("Enter a valid room ID.")).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("creates a room and navigates", async () => {
    createRoomMock.mockResolvedValueOnce({ roomId: "550e8400-e29b-41d4-a716-446655440000" });
    render(() => <LobbyPage />);

    const newRoomButton = screen.getByRole("button", { name: "New room" });
    await fireEvent.click(newRoomButton);

    expect(navigateMock).toHaveBeenCalledWith("/room/550e8400-e29b-41d4-a716-446655440000");
  });
});
