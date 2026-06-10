import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "../App";

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("App component", () => {
  beforeEach(() => {
    mockFetch.mockClear();
    window.localStorage.clear();
  });

  it("renders the channel selection step initially", () => {
    render(<App />);
    expect(screen.getByText("YouTube Transcript Search")).toBeInTheDocument();
    expect(screen.getByLabelText("ชื่อช่องหรือ URL ช่อง YouTube")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/@AssabiqoonPublisher/)).toBeInTheDocument();
  });

  it("handles form validation and video list retrieval", async () => {
    // Mock successful channel response
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        videos: [
          {
            id: "vid123",
            title: "บทเรียนคุณธรรม",
            published_at: "2026-05-15",
            thumbnail: "https://img.youtube.com/vi/vid123/mqdefault.jpg"
          }
        ]
      })
    });

    render(<App />);
    const input = screen.getByPlaceholderText(/@AssabiqoonPublisher/);
    fireEvent.change(input, { target: { value: "@MyTestChannel" } });
    
    const submitBtn = screen.getByText("ดึงวิดีโอจากช่อง ->");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    // Check we moved to step 2
    expect(screen.getByText("เลือกวิดีโอที่จะค้นหา")).toBeInTheDocument();
    expect(screen.getByText("บทเรียนคุณธรรม")).toBeInTheDocument();
  });
});
