import moment from "moment";
export const invoicesStamp = (d) => moment(d).format("YYYY-MM-DD HH:mm");
export const invoicesIsPast = (d) => moment(d).isBefore(moment());
