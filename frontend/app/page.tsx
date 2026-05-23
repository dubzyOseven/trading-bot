"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const t = localStorage.getItem("token");
    router.replace(t ? "/dashboard" : "/login");
  }, [router]);
  return null;
}
