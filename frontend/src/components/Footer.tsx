import React from "react";

const Footer: React.FC = () => (
  <footer
    className="px-6 py-3 flex flex-wrap items-center justify-between gap-2 text-xs"
    style={{ borderTop: "1px solid var(--border)", backgroundColor: "var(--surface-alt)", color: "var(--text-3)" }}
  >
    <span className="font-display uppercase tracking-widest">Urban Immo</span>
    <span>DVF · INSEE · OpenData Paris · Airparif</span>
    <span>Projet académique RNCP40875</span>
  </footer>
);

export default Footer;
