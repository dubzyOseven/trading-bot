import Image from "next/image";
import Link from "next/link";

const BRAND_NAME = "MX-Trading Bot";

type BrandLogoProps = {
  size?: "sm" | "md" | "lg";
  showName?: boolean;
  href?: string;
  className?: string;
};

const sizes = {
  sm: { w: 36, h: 27, text: "text-base" },
  md: { w: 52, h: 39, text: "text-lg" },
  lg: { w: 200, h: 150, text: "text-xl" },
};

export function BrandLogo({
  size = "sm",
  showName = true,
  href,
  className = "",
}: BrandLogoProps) {
  const s = sizes[size];
  const content = (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span
        className={`relative shrink-0 overflow-hidden rounded-md ${
          size === "lg" ? "shadow-md ring-1 ring-gray-700/40" : ""
        }`}
        style={{ width: s.w, height: s.h }}
      >
        <Image
          src="/mx-logo.png"
          alt="MX Academy"
          fill
          className="object-contain"
          priority={size === "lg"}
        />
      </span>
      {showName && (
        <span className={`font-bold tracking-tight text-white ${s.text}`}>
          {BRAND_NAME}
        </span>
      )}
    </span>
  );

  if (href) {
    return (
      <Link href={href} className="hover:opacity-90 transition-opacity">
        {content}
      </Link>
    );
  }

  return content;
}

export { BRAND_NAME };
