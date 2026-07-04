/**
 * Landing — one screen, black void. Pitch line in the voice font, the teaser
 * stream glowing beneath it, one CTA styled as a terminal prompt. No nav, no
 * feature grid. ?mock=1 is preserved into /app.
 */

import { Link, useLocation } from 'react-router-dom';
import { TeaserStream } from '../components/landing/TeaserStream';

export default function Landing() {
  const location = useLocation();
  return (
    <main className="landing">
      <h1 className="landing__pitch">Plug in a sensor. Watch it become self-aware.</h1>
      <TeaserStream />
      <Link className="landing__cta machine" to={{ pathname: '/app', search: location.search }}>
        &gt; enter the console<span className="landing__cursor">▌</span>
      </Link>
    </main>
  );
}
