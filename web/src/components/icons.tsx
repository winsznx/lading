import type { ReactElement, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 16, children, ...rest }: IconProps): ReactElement {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

export function CloseIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </Svg>
  );
}

export function LockIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <rect x="3.5" y="7" width="9" height="6.5" rx="1" />
      <path d="M5.5 7V5a2.5 2.5 0 015 0v2" />
    </Svg>
  );
}

export function TruckIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <path d="M1.5 4h8v7h-8zM9.5 6.5h3l2 2.5V11h-5" />
      <circle cx="4.5" cy="12" r="1.2" />
      <circle cx="11.5" cy="12" r="1.2" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <path d="M3.5 8.5l3 3 6-7" />
    </Svg>
  );
}

export function AlertIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <path d="M8 2l6.5 11.5h-13z" />
      <path d="M8 6.5v3M8 11.6v.1" />
    </Svg>
  );
}

export function ChevronDownIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <path d="M4 6l4 4 4-4" />
    </Svg>
  );
}

export function SunIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
    </Svg>
  );
}

export function MoonIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <path d="M13.5 9.5A5.5 5.5 0 016.5 2.5a5.5 5.5 0 107 7z" />
    </Svg>
  );
}

export function CopyIcon(props: IconProps): ReactElement {
  return (
    <Svg {...props}>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1" />
      <path d="M10.5 5.5V3.5a1 1 0 00-1-1h-6a1 1 0 00-1 1v6a1 1 0 001 1h2" />
    </Svg>
  );
}

export function SortIcon({ activeOrder, ...props }: IconProps & { activeOrder: "asc" | "desc" | null }): ReactElement {
  return (
    <Svg size={12} {...props}>
      <path d="M5 6.5L8 3.5l3 3" opacity={activeOrder === "asc" ? 1 : 0.35} />
      <path d="M5 9.5L8 12.5l3-3" opacity={activeOrder === "desc" ? 1 : 0.35} />
    </Svg>
  );
}
