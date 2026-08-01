import { afterEach, describe, expect, it, vi } from "vitest";

import { createSecuritySessionManager } from "../../frontend/src/api/security-session";
import { createCharacterApiClient } from "../../frontend/src/features/character/api/client";
import { CharacterApiError } from "../../frontend/src/features/character/api/errors";
import {
  characterErrorEnvelope,
  characterId,
  characterJsonResponse,
  characterPage,
  characterProjectId,
  characterResponse,
} from "./character-support";

afterEach(() => {
  vi.unstubAllGlobals();
});

function clientAndSession() {
  const requestSession = vi.fn().mockResolvedValue({
    csrf_token: "x".repeat(32),
    expires_in_seconds: 300,
  });
  return {
    requestSession,
    client: createCharacterApiClient(
      createSecuritySessionManager({ requestSession }),
    ),
  };
}

describe("Character API client", () => {
  it("lists with opaque keyset pagination without obtaining a security session", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(characterJsonResponse(characterPage()));
    vi.stubGlobal("fetch", fetchMock);
    const { client, requestSession } = clientAndSession();
    await expect(
      client.listCharacters({
        projectId: characterProjectId,
        limit: 10,
        cursor: "opaque+/cursor",
      }),
    ).resolves.toEqual(characterPage());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/v1/projects/${characterProjectId}/characters?limit=10&cursor=opaque%2B%2Fcursor`,
    );
    expect(requestSession).not.toHaveBeenCalled();
  });

  it("creates once with normalized complete text, CSRF, exact Location, and ETag", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      characterJsonResponse(characterResponse(), {
        status: 201,
        etag: '"1"',
        location: `/api/v1/characters/${characterId}`,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { client, requestSession } = clientAndSession();
    const result = await client.createCharacter({
      projectId: characterProjectId,
      name: " 林砚 ",
      role: " 主角 ",
      profile: "第一行\r\n第二行",
    });
    expect(result.version).toBe(1);
    expect(fetchMock).toHaveBeenCalledOnce();
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("x".repeat(32));
    if (typeof init?.body !== "string") {
      throw new Error("Expected a serialized JSON request body.");
    }
    expect(JSON.parse(init.body)).toEqual({
      name: "林砚",
      role: "主角",
      profile: "第一行\n第二行",
    });
    expect(requestSession).toHaveBeenCalledOnce();
  });

  it("gets a current Character without a session and revises once with If-Match", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        characterJsonResponse(characterResponse(), { etag: '"1"' }),
      )
      .mockResolvedValueOnce(
        characterJsonResponse(characterResponse(2), { etag: '"2"' }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { client, requestSession } = clientAndSession();
    await client.getCharacter({
      projectId: characterProjectId,
      characterId,
    });
    expect(requestSession).not.toHaveBeenCalled();
    await client.reviseCharacter({
      projectId: characterProjectId,
      characterId,
      etag: '"1"',
      name: "林砚",
      role: "",
      profile: "",
    });
    const init = fetchMock.mock.calls[1]?.[1];
    expect(init?.method).toBe("PUT");
    expect(new Headers(init?.headers).get("If-Match")).toBe('"1"');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each([
    [
      "project",
      () => clientAndSession().client.listCharacters({ projectId: "bad" }),
    ],
    [
      "limit",
      () =>
        clientAndSession().client.listCharacters({
          projectId: characterProjectId,
          limit: 0,
        }),
    ],
    [
      "cursor",
      () =>
        clientAndSession().client.listCharacters({
          projectId: characterProjectId,
          cursor: "",
        }),
    ],
    [
      "character",
      () =>
        clientAndSession().client.getCharacter({
          projectId: characterProjectId,
          characterId: "bad",
        }),
    ],
  ])("rejects invalid %s input before fetch", async (_label, operation) => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    await expect(operation()).rejects.toBeInstanceOf(CharacterApiError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps 409 distinct and safely preserves a valid 412 conflict", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        characterJsonResponse(characterErrorEnvelope("CHARACTER_ID_CONFLICT"), {
          status: 409,
        }),
      )
      .mockResolvedValueOnce(
        characterJsonResponse(
          characterErrorEnvelope("CHARACTER_VERSION_CONFLICT", {
            expected_version: 1,
            actual_version: 2,
          }),
          { status: 412 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { client } = clientAndSession();
    await expect(
      client.createCharacter({
        projectId: characterProjectId,
        name: "林砚",
        role: "",
        profile: "private",
      }),
    ).rejects.toMatchObject({ kind: "character_id_conflict" });
    await expect(
      client.reviseCharacter({
        projectId: characterProjectId,
        characterId,
        etag: '"1"',
        name: "林砚",
        role: "",
        profile: "private",
      }),
    ).rejects.toMatchObject({
      kind: "version_conflict",
      conflict: { expectedVersion: 1, actualVersion: 2 },
    });
  });

  it.each([
    ["network", () => Promise.reject(new TypeError("secret"))],
    [
      "server",
      () =>
        Promise.resolve(
          characterJsonResponse(characterErrorEnvelope("PRIVATE"), {
            status: 503,
          }),
        ),
    ],
    [
      "contract",
      () =>
        Promise.resolve(
          characterJsonResponse(characterResponse(), {
            status: 201,
            etag: '"1"',
            location: "/wrong",
          }),
        ),
    ],
  ])(
    "marks a started create %s failure outcome unknown",
    async (_label, response) => {
      vi.stubGlobal(
        "fetch",
        vi.fn<typeof fetch>().mockImplementation(response),
      );
      const { client } = clientAndSession();
      await expect(
        client.createCharacter({
          projectId: characterProjectId,
          name: "林砚",
          role: "",
          profile: "CHARACTER_FRONTEND_SECRET_CANARY",
        }),
      ).rejects.toMatchObject({
        kind: "write_outcome_unknown",
        code: "CHARACTER_CREATE_OUTCOME_UNKNOWN",
      });
    },
  );

  it("rejects invalid text and ETag before obtaining a session", async () => {
    const { client, requestSession } = clientAndSession();
    await expect(
      client.createCharacter({
        projectId: characterProjectId,
        name: "",
        role: "",
        profile: "",
      }),
    ).rejects.toMatchObject({ kind: "validation" });
    await expect(
      client.reviseCharacter({
        projectId: characterProjectId,
        characterId,
        etag: "weak",
        name: "林砚",
        role: "",
        profile: "",
      }),
    ).rejects.toMatchObject({ kind: "contract" });
    expect(requestSession).not.toHaveBeenCalled();
  });

  it("marks a started revise network failure outcome unknown", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockRejectedValue(new TypeError("private")),
    );
    const { client } = clientAndSession();
    await expect(
      client.reviseCharacter({
        projectId: characterProjectId,
        characterId,
        etag: '"1"',
        name: "林砚",
        role: "",
        profile: "private",
      }),
    ).rejects.toMatchObject({
      kind: "write_outcome_unknown",
      code: "CHARACTER_SAVE_OUTCOME_UNKNOWN",
    });
  });

  it("rejects unexpected successful statuses and non-incrementing PUT versions", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        characterJsonResponse(characterPage(), { status: 201 }),
      )
      .mockResolvedValueOnce(
        characterJsonResponse(characterResponse(), {
          status: 201,
          etag: '"1"',
        }),
      )
      .mockResolvedValueOnce(
        characterJsonResponse(characterResponse(), { etag: '"1"' }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { client } = clientAndSession();
    await expect(
      client.listCharacters({ projectId: characterProjectId }),
    ).rejects.toMatchObject({ kind: "contract" });
    await expect(
      client.getCharacter({ projectId: characterProjectId, characterId }),
    ).rejects.toMatchObject({ kind: "contract" });
    await expect(
      client.reviseCharacter({
        projectId: characterProjectId,
        characterId,
        etag: '"1"',
        name: "林砚",
        role: "主角",
        profile: "秘密档案\n第二行",
      }),
    ).rejects.toMatchObject({ kind: "write_outcome_unknown" });
  });
});
