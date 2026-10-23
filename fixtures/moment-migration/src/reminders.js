import moment from "moment-timezone";

export function nextReminder(appointment, clinicZone) {
  return moment.tz(appointment.at, clinicZone)
    .subtract(1, "day")
    .set({ hour: 9, minute: 0, second: 0, millisecond: 0 })
    .toISOString();
}
