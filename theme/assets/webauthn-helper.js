/**
 * webauthn-helper.js — WebAuthn / Passkeys helper for Anvil
 * =========================================================
 * Provides window.webauthnRegister() and window.webauthnAuthenticate()
 * for biometric login (fingerprint, Face ID, device PIN).
 *
 * Called from Anvil client-side Python via anvil.js.
 */
(function () {
  'use strict';

  // ── Base64URL ↔ ArrayBuffer helpers ──────────────────────────

  function base64urlToBuffer(base64url) {
    // Convert base64url → standard base64
    var base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
    // Pad with '='
    while (base64.length % 4 !== 0) { base64 += '='; }
    var binary = atob(base64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  function bufferToBase64url(buffer) {
    var bytes = new Uint8Array(buffer);
    var binary = '';
    for (var i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    var base64 = btoa(binary);
    return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  // ── Feature detection ────────────────────────────────────────

  window.isWebAuthnSupported = function () {
    return !!(window.PublicKeyCredential);
  };

  /**
   * Check if platform authenticator (fingerprint/Face ID/PIN) is available.
   * Returns a Promise that resolves to true/false.
   */
  window.isPasskeyAvailable = function () {
    if (!window.PublicKeyCredential) {
      return Promise.resolve(false);
    }
    if (typeof PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable === 'function') {
      return PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
    }
    return Promise.resolve(false);
  };

  // ── Registration (تسجيل بصمة جديدة) ──────────────────────────

  /**
   * Register a new WebAuthn credential.
   * @param {string} optionsJSON - JSON string from server (py_webauthn options_to_json)
   * @returns {Promise<string>} - JSON string of the credential response
   */
  window.webauthnRegister = function (optionsJSON) {
    var options = typeof optionsJSON === 'string' ? JSON.parse(optionsJSON) : optionsJSON;

    // Convert base64url fields to ArrayBuffer
    options.challenge = base64urlToBuffer(options.challenge);
    options.user.id = base64urlToBuffer(options.user.id);

    if (options.excludeCredentials) {
      options.excludeCredentials = options.excludeCredentials.map(function (cred) {
        return {
          id: base64urlToBuffer(cred.id),
          type: cred.type || 'public-key',
          transports: cred.transports || []
        };
      });
    }

    // Force platform authenticator (Touch ID / Face ID / Windows Hello)
    // This prevents the browser from showing QR code for phone-based auth
    if (!options.authenticatorSelection) {
      options.authenticatorSelection = {};
    }
    options.authenticatorSelection.authenticatorAttachment = 'platform';
    options.authenticatorSelection.userVerification = 'required';
    options.authenticatorSelection.residentKey = 'preferred';

    return navigator.credentials.create({ publicKey: options })
      .then(function (credential) {
        // Convert ArrayBuffer fields to base64url for JSON transmission
        var response = {
          id: credential.id,
          rawId: bufferToBase64url(credential.rawId),
          type: credential.type,
          response: {
            attestationObject: bufferToBase64url(credential.response.attestationObject),
            clientDataJSON: bufferToBase64url(credential.response.clientDataJSON)
          }
        };

        // Include transports if available (for future allowCredentials hints)
        if (typeof credential.response.getTransports === 'function') {
          response.response.transports = credential.response.getTransports();
        }

        return JSON.stringify(response);
      });
  };

  // ── Authentication (تسجيل دخول بالبصمة) ─────────────────────

  /**
   * Authenticate with an existing WebAuthn credential.
   * @param {string} optionsJSON - JSON string from server (py_webauthn options_to_json)
   * @returns {Promise<string>} - JSON string of the assertion response
   */
  window.webauthnAuthenticate = function (optionsJSON) {
    var options = typeof optionsJSON === 'string' ? JSON.parse(optionsJSON) : optionsJSON;

    // Convert base64url fields to ArrayBuffer
    options.challenge = base64urlToBuffer(options.challenge);

    if (options.allowCredentials) {
      options.allowCredentials = options.allowCredentials.map(function (cred) {
        return {
          id: base64urlToBuffer(cred.id),
          type: cred.type || 'public-key',
          transports: cred.transports || []
        };
      });
    }

    // Force platform authenticator (Touch ID / Face ID / Windows Hello)
    options.userVerification = 'required';

    // Filter allowCredentials to only platform transports (no hybrid/ble = no QR)
    if (options.allowCredentials) {
      options.allowCredentials = options.allowCredentials.map(function (cred) {
        return {
          id: cred.id,
          type: cred.type || 'public-key',
          transports: ['internal']
        };
      });
    }

    return navigator.credentials.get({ publicKey: options })
      .then(function (assertion) {
        var response = {
          id: assertion.id,
          rawId: bufferToBase64url(assertion.rawId),
          type: assertion.type,
          response: {
            authenticatorData: bufferToBase64url(assertion.response.authenticatorData),
            clientDataJSON: bufferToBase64url(assertion.response.clientDataJSON),
            signature: bufferToBase64url(assertion.response.signature)
          }
        };

        // Include userHandle if present (for resident credentials / passkeys)
        if (assertion.response.userHandle) {
          response.response.userHandle = bufferToBase64url(assertion.response.userHandle);
        }

        return JSON.stringify(response);
      });
  };

  // Log availability on load (debug only)
  if (window.debugLog) {
    window.isPasskeyAvailable().then(function (available) {
      window.debugLog('[WebAuthn] Platform authenticator available:', available);
    });
  }

})();
