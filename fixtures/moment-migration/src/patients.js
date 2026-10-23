import moment from "moment";
export const patientsStamp = (d) => moment(d).format("YYYY-MM-DD HH:mm");
export const patientsIsPast = (d) => moment(d).isBefore(moment());
