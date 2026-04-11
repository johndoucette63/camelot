import MuteList from "../components/MuteList";
import NotificationSinkForm from "../components/NotificationSinkForm";
import ThresholdForm from "../components/ThresholdForm";

export default function Settings() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-2xl font-bold text-gray-800">Settings</h1>
      <ThresholdForm />
      <MuteList />
      <NotificationSinkForm />
    </div>
  );
}
