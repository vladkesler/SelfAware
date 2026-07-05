/**
 * Navbar — top row for the single-page Landing site. Fixed and transparent
 * at rest, gains a frosted background once scrolled. Never rendered on /app.
 * About/Industry/Team are in-page anchors (same page, smooth-scrolled); Start
 * Now forwards location.search so ?mock=1 survives, same pattern as the
 * landing CTA.
 */

import { Link, useLocation } from 'react-router-dom';
import { useScrolled } from '../../hooks/useScrolled';

export function Navbar() {
  const location = useLocation();
  const scrolled = useScrolled();
  return (
    <header className={`navbar${scrolled ? ' navbar--scrolled' : ''}`}>
      <Link className="navbar__logo machine" to="/">
        ◌ <span className="navbar__wordmark">SelfAware</span>
      </Link>
      <nav className="navbar__links machine">
        <a className="navbar__link" href="#about">
          About
        </a>
        <a className="navbar__link" href="#industry">
          Industry
        </a>
        <a className="navbar__link" href="#team">
          Team
        </a>
        <a className="navbar__link" href="/scalability.html" target="_blank" rel="noreferrer">
          Scalability
        </a>
        <Link className="navbar__link" to={{ pathname: '/app', search: location.search }}>
          Start Now
        </Link>
      </nav>
    </header>
  );
}
