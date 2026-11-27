/* The authored SVG diagrams. Shown instead of the 3D scene when motion or WebGL is unavailable. */
export function Still({ name, alt }: { name: string; alt: string }) {
  return (
    <figure className="still">
      <picture>
        <source media="(max-width: 639px)" srcSet={`/stills/${name}.phone.svg`} />
        <img src={`/stills/${name}.svg`} alt={alt} loading="lazy" />
      </picture>
    </figure>
  );
}
