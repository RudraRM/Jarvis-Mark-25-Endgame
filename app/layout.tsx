import "./globals.css";
import { AudioProvider } from "@/components/AudioProvider";
export const metadata = { title: "Jarvis Mark 85", description: "Voice-operated neural interface" };
export default function Layout({children}:{children:React.ReactNode}) { return <html lang="en"><body><AudioProvider>{children}</AudioProvider></body></html> }
