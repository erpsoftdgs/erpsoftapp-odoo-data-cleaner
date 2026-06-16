import { redirect } from 'next/navigation';
import { getSession } from '@/lib/auth';
import HomeClient from './HomeClient';

export const dynamic = 'force-dynamic';

export default async function Home() {
  const session = await getSession();
  if (!session) redirect('/login');
  return <HomeClient />;
}
