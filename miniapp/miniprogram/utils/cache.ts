interface TimedCacheEntry<TValue> {
  value?: TValue;
  expiresAt: number;
  pending?: Promise<TValue>;
}

export interface CachedLoaderOptions {
  ttlMs: number;
  forceRefresh?: boolean;
}

export function createCachedLoader<TValue, TArgs extends unknown[]>(
  loader: (...args: TArgs) => Promise<TValue>,
  getKey: (...args: TArgs) => string
) {
  const cache = new Map<string, TimedCacheEntry<TValue>>();

  return async (...args: [...TArgs, CachedLoaderOptions?]): Promise<TValue> => {
    const maybeOptions = args[args.length - 1] as CachedLoaderOptions | undefined;
    const hasOptions = Boolean(
      maybeOptions
        && typeof maybeOptions === "object"
        && "ttlMs" in maybeOptions
    );
    const options = hasOptions ? maybeOptions : undefined;
    const loaderArgs = (hasOptions ? args.slice(0, -1) : args) as TArgs;
    const key = getKey(...loaderArgs);
    const now = Date.now();
    const entry = cache.get(key);

    if (!options?.forceRefresh && entry?.value !== undefined && entry.expiresAt > now) {
      return entry.value;
    }
    if (!options?.forceRefresh && entry?.pending) {
      return entry.pending;
    }

    const ttlMs = options?.ttlMs ?? 0;
    const pending = loader(...loaderArgs)
      .then((value) => {
        cache.set(key, {
          value,
          expiresAt: Date.now() + ttlMs
        });
        return value;
      })
      .catch((error) => {
        cache.delete(key);
        throw error;
      });

    cache.set(key, {
      value: entry?.value,
      expiresAt: entry?.expiresAt ?? 0,
      pending
    });
    return pending;
  };
}
