// Ancora : connexion par Face ID / Touch ID (clés d'accès WebAuthn). Sans dépendance.
(function () {
  const toBytes = (b64url) => {
    const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((b64url.length + 3) % 4);
    return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  };
  const toB64url = (buffer) => btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

  async function post(url, body) {
    const response = await fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Ancora": "1" },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Opération impossible.");
    return data;
  }

  function friendly(error) {
    if (error && error.name === "NotAllowedError") return "Opération annulée.";
    if (error && error.name === "InvalidStateError") return "Cet appareil est déjà enregistré.";
    if (error && error.name === "SecurityError") return "Adresse non sécurisée : Face ID exige HTTPS.";
    return (error && error.message) || "Opération impossible.";
  }

  const label = () => {
    const ua = navigator.userAgent;
    if (/iPhone|iPad/.test(ua)) return "Face ID";
    if (/Macintosh/.test(ua)) return "Touch ID";
    if (/Windows/.test(ua)) return "Windows Hello";
    if (/Android/.test(ua)) return "l'empreinte ou le visage";
    return "une clé d'accès";
  };

  async function login() {
    const { challenge, options } = await post("/connexion/cle/options");
    options.challenge = toBytes(options.challenge);
    (options.allowCredentials || []).forEach((c) => { c.id = toBytes(c.id); });
    const credential = await navigator.credentials.get({ publicKey: options });
    const r = credential.response;
    return post("/connexion/cle/verifier", { challenge, credential: {
      id: credential.id, rawId: toB64url(credential.rawId), type: credential.type,
      authenticatorAttachment: credential.authenticatorAttachment, clientExtensionResults: {},
      response: {
        clientDataJSON: toB64url(r.clientDataJSON), authenticatorData: toB64url(r.authenticatorData),
        signature: toB64url(r.signature), userHandle: r.userHandle ? toB64url(r.userHandle) : null,
      },
    } });
  }

  async function register(extra) {
    const { challenge, options } = await post("/connexion/cle/ajout/options", extra);
    options.challenge = toBytes(options.challenge);
    options.user.id = toBytes(options.user.id);
    (options.excludeCredentials || []).forEach((c) => { c.id = toBytes(c.id); });
    const credential = await navigator.credentials.create({ publicKey: options });
    const r = credential.response;
    return post("/connexion/cle/ajout", { challenge, credential: {
      id: credential.id, rawId: toB64url(credential.rawId), type: credential.type,
      authenticatorAttachment: credential.authenticatorAttachment, clientExtensionResults: {},
      response: {
        clientDataJSON: toB64url(r.clientDataJSON), attestationObject: toB64url(r.attestationObject),
        transports: r.getTransports ? r.getTransports() : [],
      },
    } });
  }

  window.AncoraPasskey = {
    supported: () => !!(window.PublicKeyCredential && navigator.credentials && window.isSecureContext),
    label, login, register, friendly,
  };
})();
