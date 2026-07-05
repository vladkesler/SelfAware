/**
 * Landing — single-page site. Hero void, why-statement, About/Industry/Team
 * sections (reached via navbar anchors), footer. ?mock=1 is preserved into
 * /app through the hero CTA, the closing CTA, and the navbar's Start Now.
 *
 * Copy follows the console's own story (fail → verbatim traceback → repair →
 * admitted): the page never claims more than the loop can prove.
 */

import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { TeaserStream } from '../components/landing/TeaserStream';
import { LoopDiagram } from '../components/landing/LoopDiagram';
import { Navbar } from '../components/nav/Navbar';
import { useInView } from '../hooks/useInView';
import { useScrollProgress } from '../hooks/useScrollProgress';

const LINKEDIN_PATH =
  'M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9h4v12H3V9Zm7 0h3.83v1.64h.05c.53-1 1.83-2.06 3.77-2.06 4.03 0 4.77 2.65 4.77 6.1V21h-4v-5.6c0-1.34-.02-3.06-1.87-3.06-1.87 0-2.16 1.46-2.16 2.96V21h-4V9Z';

interface TeamMember {
  name: string;
  role: string;
  photo: string;
  linkedin?: string; // TODO: fill in once each teammate's LinkedIn URL is available
}

const TEAM: TeamMember[] = [
  { name: 'Gyula', role: 'Market expert', photo: '/team/gyula.png' },
  { name: 'Vladimir', role: 'Technology expert', photo: '/team/vladimir.jpeg' },
  { name: 'Mark', role: 'Technology expert', photo: '/team/mark.jpeg' },
  { name: 'Aleksei', role: 'Technology expert', photo: '/team/aleksei.jpeg' },
  { name: 'Fernanda', role: 'Technology expert', photo: '/team/fernanda.png' },
];

interface Fit {
  title: string;
  body: string;
}

const FITS: Fit[] = [
  {
    title: 'Robotics',
    body: 'A robot should not wait for a firmware engineer every time it grows a new gripper. New hardware introduces itself, proves itself, and gets to work.',
  },
  {
    title: 'Industrial systems',
    body: 'One admission loop, four device classes — analog, I2C/SPI, pulse-timing, output — covers effectively any sensor or actuator a plant, line, or fleet needs. Not a robotics demo; the same loop scales to whatever’s plugged in.',
  },
  {
    title: 'Connected devices',
    body: 'Every product line ships new sensors on old firmware timelines. Turn bring-up from a sprint into a loop that runs while you watch.',
  },
  {
    title: 'Physical AI',
    body: 'An agent that acts on a lying sensor acts wrong with confidence. Give it hands that have already been checked against physics.',
  },
];

export default function Landing() {
  const location = useLocation();
  const [whyRef, whyVisible] = useInView<HTMLDivElement>();
  const [aboutRef, aboutVisible] = useInView<HTMLDivElement>();
  const heroFade = useScrollProgress();

  useEffect(() => {
    if (!location.hash) return;
    document.querySelector(location.hash)?.scrollIntoView({ behavior: 'smooth' });
  }, [location.hash]);

  const consoleTo = { pathname: '/app', search: location.search };

  return (
    <>
      <main className="landing">
        <Navbar />
        <div
          className="landing__content"
          style={{
            opacity: 1 - heroFade,
            transform: `translateY(${heroFade * -40}px) scale(${1 - heroFade * 0.06})`,
          }}
        >
          <h1 className="landing__pitch">
            Plug in a <span className="landing__pitch-strong">sensor</span>.
            <br /> Watch it become{' '}
            <span className="landing__pitch-strong landing__pitch-accent">self-aware</span>.
          </h1>
          <TeaserStream />
          <Link className="landing__cta machine" to={consoleTo}>
            &gt; enter the console<span className="landing__cursor">▌</span>
          </Link>
        </div>
      </main>

      <section className="landing-why">
        <div ref={whyRef} className={`landing-why__content${whyVisible ? ' is-visible' : ''}`}>
          <p className="landing-why__beat">No human wrote this driver.</p>
          <p className="landing-why__beat">No human tested it either.</p>
          <p className="landing-why__beat landing-why__beat--accent">The hardware did.</p>
        </div>
      </section>

      <section id="about" className="landing-section landing-about">
        <div
          ref={aboutRef}
          className={`landing-about__content${aboutVisible ? ' is-visible' : ''}`}
        >
          <p className="landing-section__eyebrow machine">about</p>
          <h2 className="landing-section__lead">
            Before AI can act in the physical world, it has to know what is real.
          </h2>
          <div className="landing-about__body">
            <p>
              A sensor that returns a number is not a sensor you can trust. A shorted pin reads
              as a temperature. A floating wire reads as a heartbeat. A number that looks right
              can still be a lie.
            </p>
            <p>
              SelfAware is the admission layer for physical AI. Plug in a device nobody wrote a
              driver for, and an agent writes the driver, deploys it to a real board over USB
              serial, and test-reads it on live hardware. When an attempt fails, the board's own
              traceback — verbatim, never paraphrased — steers the repair.
            </p>
            <p>
              Then the reading has to prove itself: sit in a plausible range, and move when the
              world moves — cover the light sensor and the number must fall. Only then is the
              driver admitted to the registry, where it becomes a live tool —{' '}
              <code className="machine">read_ldr</code>, <code className="machine">set_relay</code>{' '}
              — that any agent can call.
            </p>
            <p className="landing-about__close">
              Others distribute trust. SelfAware manufactures it.
            </p>
          </div>
        </div>
      </section>

      <section id="industry" className="landing-section">
        <p className="landing-section__eyebrow machine">who it&apos;s for</p>
        <h2 className="landing-section__lead">
          Every physical system is becoming software-defined.
        </h2>
        <div className="industry-lead">
          <p>
            SelfAware is built for teams whose software does not just read data — it depends on
            the physical world being true, whatever the device, at whatever scale they&apos;re
            running it.
          </p>
        </div>

        <div className="industry-fits">
          {FITS.map((fit) => (
            <div className="industry-fits__item" key={fit.title}>
              <p className="industry-fits__title">{fit.title}</p>
              <p className="industry-fits__body">{fit.body}</p>
            </div>
          ))}
        </div>

        <div className="industry-provides">
          <LoopDiagram />

          <div className="industry-provides__content">
            <h3 className="landing-section__lead">From unknown wire to trusted tool</h3>
            <p className="industry-provides__text">
              The old way: a human writes the driver, a human tests it, one device at a time —
              and every agent downstream inherits their trust on faith.
            </p>
            <p className="industry-provides__text">
              SelfAware closes the loop instead. The driver is generated, deployed to the live
              board, observed, validated against physics, and only then registered as a callable
              tool. Hardware gets admitted the way software got tools: discovered, tested,
              trusted, called.
            </p>
          </div>
        </div>
      </section>

      <section id="team" className="landing-section">
        <p className="landing-section__eyebrow machine">team</p>
        <h2 className="landing-section__lead">Our team</h2>
        <div className="team-grid">
          {TEAM.map((member) => (
            <div className="team-card" key={member.name}>
              <img
                className="team-card__avatar"
                src={member.photo}
                alt={member.name}
                loading="lazy"
              />
              <span className="team-card__name">{member.name}</span>
              <span className="team-card__role">{member.role}</span>
              <a
                className="team-card__linkedin"
                href={member.linkedin ?? '#'}
                aria-label={`${member.name} on LinkedIn (link coming soon)`}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d={LINKEDIN_PATH} />
                </svg>
              </a>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section landing-closing">
        <p className="landing-section__lead landing-closing__text">
          Reliability is a property of the loop, not the model.
        </p>
        <Link className="landing__cta machine" to={consoleTo}>
          &gt; enter the console<span className="landing__cursor">▌</span>
        </Link>
      </section>

      <footer className="landing-footer">
        <div className="landing-footer__content">
          <span className="landing-footer__name machine">SelfAware</span>
          <p className="landing-footer__tagline">Verified hands for AI agents in the physical world.</p>
          <div className="landing-footer__socials">
            <a
              className="landing-footer__social"
              href="#"
              aria-label="SelfAware on LinkedIn (coming soon)"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d={LINKEDIN_PATH} />
              </svg>
            </a>
            <a
              className="landing-footer__social"
              href="#"
              aria-label="SelfAware on X (coming soon)"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M18.9 3H21l-6.6 7.54L22.2 21h-6.3l-4.94-6.46L4.98 21H2.87l7.06-8.07L2 3h6.46l4.47 5.9L18.9 3Zm-1.1 16.2h1.17L7.28 4.72H6.02L17.8 19.2Z" />
              </svg>
            </a>
            <a
              className="landing-footer__social"
              href="#"
              aria-label="SelfAware on YouTube (coming soon)"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M21.6 7.2s-.21-1.49-.87-2.15c-.83-.87-1.76-.87-2.19-.92C15.44 4 12 4 12 4h-.01s-3.44 0-6.54.13c-.43.05-1.36.05-2.19.92-.66.66-.87 2.15-.87 2.15S2 8.94 2 10.68v1.63c0 1.74.18 3.48.18 3.48s.21 1.49.87 2.15c.83.87 1.92.84 2.4.93 1.74.17 7.4.22 7.4.22s3.44 0 6.54-.13c.43-.05 1.36-.05 2.19-.92.66-.66.87-2.15.87-2.15s.18-1.74.18-3.48v-1.63c0-1.74-.18-3.48-.18-3.48ZM9.98 14.5v-5.3l5.1 2.66-5.1 2.64Z" />
              </svg>
            </a>
          </div>
        </div>
      </footer>
    </>
  );
}
