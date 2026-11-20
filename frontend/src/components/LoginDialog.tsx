import { type FormEvent, useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import Modal from "./Modal";
import { Alert, Field, PrimaryButton, SecondaryButton } from "./ui";

export default function LoginDialog({ onClose }: { onClose: () => void }) {
  const { login } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(password);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar sesión");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Acceso de editor"
      eyebrow="Administración"
      onClose={onClose}
      footer={
        <>
          <SecondaryButton type="button" onClick={onClose} className="flex-1">
            Cancelar
          </SecondaryButton>
          <PrimaryButton type="submit" form="login-form" disabled={busy || !password} className="flex-1">
            {busy ? "Verificando…" : "Entrar"}
          </PrimaryButton>
        </>
      }
    >
      <form id="login-form" onSubmit={submit} className="flex flex-col gap-4">
        <p className="text-[13px] text-stone-500">
          Consultar el catálogo y usar el recomendador es libre. Para editar, añadir o importar revistas
          se requiere la contraseña de editor.
        </p>
        <Field
          label="Contraseña"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {error && <Alert>{error}</Alert>}
      </form>
    </Modal>
  );
}
