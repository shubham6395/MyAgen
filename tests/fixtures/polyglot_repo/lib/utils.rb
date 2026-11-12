module Utils
  def self.greet(name)
    "hello #{name}"
  end
end

class Greeter
  def initialize(name)
    @name = name
  end
end