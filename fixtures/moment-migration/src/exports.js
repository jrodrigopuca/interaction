import moment from "moment";
export const exportsStamp = (d) => moment(d).format("YYYY-MM-DD HH:mm");
export const exportsIsPast = (d) => moment(d).isBefore(moment());
