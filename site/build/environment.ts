const REQUIRED_CLIENT_ENVIRONMENT = [
  "VITE_GOOGLE_MAPS_API_KEY",
  "VITE_FORECAST_API_URL",
] as const;

export function validateBuildEnvironment(
  environment: Record<string, string | undefined>,
  options: { requireHttps?: boolean } = {},
): void {
  const missing = REQUIRED_CLIENT_ENVIRONMENT.filter(
    (name) => !environment[name]?.trim(),
  );
  if (missing.length > 0) {
    throw new Error(
      `静的ビルドに必要な環境変数が設定されていません: ${missing.join(", ")}`,
    );
  }

  const forecastApiUrl = environment.VITE_FORECAST_API_URL as string;
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(forecastApiUrl);
  } catch {
    throw new Error("VITE_FORECAST_API_URL には絶対URLを指定してください。");
  }
  if (!["http:", "https:"].includes(parsedUrl.protocol)) {
    throw new Error(
      "VITE_FORECAST_API_URL には http または https のURLを指定してください。",
    );
  }
  if (options.requireHttps && parsedUrl.protocol !== "https:") {
    throw new Error(
      "配信用の VITE_FORECAST_API_URL には https のURLを指定してください。",
    );
  }
}
