import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, onUnauthorized, setToken } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(!getToken());

  useEffect(() => {
    onUnauthorized(() => { setToken(null); setUser(null); });
    if (getToken()) {
      api.me().then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
    }
  }, []);

  const start = useCallback((result) => {
    setToken(result.access_token);
    setUser(result.user);
    return result.user;
  }, []);
  const signIn = useCallback(async (email, password) => start(await api.login(email, password)), [start]);
  const register = useCallback(async (body) => start(await api.register(body)), [start]);
  const signOut = useCallback(() => { setToken(null); setUser(null); }, []);
  const value = useMemo(() => ({ user, ready, signIn, register, signOut, setUser }), [user, ready, signIn, register, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
