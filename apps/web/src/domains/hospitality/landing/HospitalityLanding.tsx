import Link from "next/link";
import styles from "./HospitalityLanding.module.css";

export function HospitalityLanding() {
  return (
    <main className={styles.landing}>
      <p style={{ color: "#6b6358", letterSpacing: ".08em", textTransform: "uppercase" }}>
        StayLead · Hospitality
      </p>
      <h1>Ask about your stay</h1>
      <p>
        Get clear answers about each demo hotel. No sign-up is needed.
      </p>
      <p className={styles.disclosure}>Demo experience using synthetic hotel information.</p>
      <ul className={styles.hotelList} aria-label="Demo hotels">
        <li><Link className={styles.hotelLink} href="/hotels/harbor-city-demo/chat">Harbor City Demo</Link></li>
        <li><Link className={styles.hotelLink} href="/hotels/lagoon-family-demo/chat">Lagoon Family Demo</Link></li>
        <li><Link className={styles.hotelLink} href="/hotels/pine-ridge-demo/chat">Pine Ridge Demo</Link></li>
      </ul>
    </main>
  );
}
