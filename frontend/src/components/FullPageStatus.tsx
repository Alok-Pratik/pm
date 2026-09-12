type FullPageStatusProps = {
  loadingText: string;
  error?: string;
};

export const FullPageStatus = ({ loadingText, error }: FullPageStatusProps) => (
  <main className="grid min-h-screen place-items-center p-6">
    {error ? <p role="alert">{error}</p> : <p>{loadingText}</p>}
  </main>
);
