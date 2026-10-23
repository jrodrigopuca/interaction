import moment from "moment";
export const settingsStamp = (d) => moment(d).format("YYYY-MM-DD HH:mm");
export const settingsIsPast = (d) => moment(d).isBefore(moment());
