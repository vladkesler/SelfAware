/**
 * Landing — single-page site. Hero void, why-statement, About/Industry/Team
 * sections (reached via navbar anchors), footer. ?mock=1 is preserved into
 * /app through both the CTA and the navbar's Start Now link.
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
    body: 'Before a robot acts, it needs to know its sensors, actuators, and environment are reporting correctly.',
  },
  {
    title: 'Labs',
    body: 'Experiments need proof that devices are connected, calibrated, and producing reliable signals before results are trusted.',
  },
  {
    title: 'Connected devices',
    body: 'Hardware products need a repeatable way to validate sensors before they ship, update, or run in the field.',
  },
  {
    title: 'Physical AI',
    body: 'AI agents need verified access to real-world state before they can safely observe, decide, or act.',
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
          <Link className="landing__cta machine" to={{ pathname: '/app', search: location.search }}>
            &gt; start now<span className="landing__cursor">▌</span>
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
          <div className="landing-about__body">
            <p className="landing-about__lead">
              Before AI can act in the physical world, it needs to know what is real.
            </p>
            <p>SelfAware is the verification loop for physical AI.</p>
            <p>
              It helps devices prove that their sensors are connected, readable, plausible, and
              trusted before software or AI depends on them.
            </p>
            <p>
              A sensor is not useful because it returns a number. It is useful when the system
              can prove the hardware actually works.
            </p>          </div>
        </div>
      </section>

      <section id="industry" className="landing-section">
        <h2 className="landing-about__lead">Every physical system is becoming software-defined.</h2>
        <div className="industry-lead">
          <p>
            SelfAware is built for teams creating products where software does not just read
            data, it depends on the physical world being true.
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
            <h3 className="landing-about__lead">What SelfAware provides</h3>

            <p className="industry-provides__text">
              The old stack was dashboards, alerts, and manual debugging.
            </p>

            <p className="industry-provides__text">
              The next stack is physical capabilities that can be discovered, tested, trusted,
              and called by software.
              <br />

              <br />
              SelfAware turns raw sensors into trusted capabilities through a closed loop:
            </p>
          </div>
        </div >
      </section >

      <section id="team" className="landing-section">
        <h2 className="landing-about__lead">Our team</h2>
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
        <p className="landing-about__lead landing-closing__text">
          Reliability is a property of the loop, not the model.
        </p>
      </section>

      <footer className="landing-footer">
        <div className="landing-footer__content">
          <span className="landing-footer__name machine">SelfAware</span>
          <p className="landing-footer__tagline">The verification loop for physical AI.</p>
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
