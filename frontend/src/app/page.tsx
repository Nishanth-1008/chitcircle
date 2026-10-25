import { redirect } from 'next/navigation';

export default function Root() {
  redirect('/app/home'); // the app shell sends signed-out visitors to /welcome
}
