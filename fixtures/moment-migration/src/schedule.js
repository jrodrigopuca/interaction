import moment from "moment";
export const scheduleStamp = (d) => moment(d).format("YYYY-MM-DD HH:mm");
export const scheduleIsPast = (d) => moment(d).isBefore(moment());
