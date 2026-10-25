export type Institution = {
  id: string
  slug: string
  name: string
  status: string
  branding: Record<string, unknown>
}

export type InstitutionUpdate = {
  name?: string
  branding?: Record<string, unknown>
}

export interface InstitutionService {
  getCurrent(signal?: AbortSignal): Promise<Institution>
  updateCurrent(update: InstitutionUpdate, signal?: AbortSignal): Promise<Institution>
}

export class HttpInstitutionService implements InstitutionService {
  constructor(
    private readonly baseUrl: string,
    private readonly getAccessToken: () => Promise<string>,
  ) {}

  private async request<T>(
    path: string,
    init: RequestInit,
    signal?: AbortSignal,
  ): Promise<T> {
    const token = await this.getAccessToken()
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        "X-Correlation-ID": crypto.randomUUID(),
        ...init.headers,
      },
    })
    if (!response.ok) {
      throw new Error(`Institution request failed with status ${response.status}`)
    }
    return response.json() as Promise<T>
  }

  getCurrent(signal?: AbortSignal): Promise<Institution> {
    return this.request("/api/v1/institutions/current", { method: "GET" }, signal)
  }

  updateCurrent(update: InstitutionUpdate, signal?: AbortSignal): Promise<Institution> {
    return this.request(
      "/api/v1/institutions/current",
      { method: "PATCH", body: JSON.stringify(update) },
      signal,
    )
  }
}

export class MockInstitutionService implements InstitutionService {
  private institution: Institution = {
    id: "11111111-1111-1111-1111-111111111111",
    slug: "northstar",
    name: "Northstar International School",
    status: "active",
    branding: {},
  }

  async getCurrent(): Promise<Institution> {
    return structuredClone(this.institution)
  }

  async updateCurrent(update: InstitutionUpdate): Promise<Institution> {
    this.institution = {
      ...this.institution,
      ...update,
      branding: update.branding ?? this.institution.branding,
    }
    return structuredClone(this.institution)
  }
}
