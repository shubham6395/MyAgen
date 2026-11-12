const mongoose = require("mongoose");

const userSchema = new mongoose.Schema({
  email: { type: String, required: true, unique: true },
  name: { type: String },
  active: { type: Boolean, default: true },
});

module.exports = mongoose.model("User", userSchema);