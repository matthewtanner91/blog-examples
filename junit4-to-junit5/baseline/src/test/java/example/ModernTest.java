package example;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import static org.junit.jupiter.api.Assertions.assertEquals;
class ModernTest {
  @Test void newBehavior() { assertEquals(3, 1 + 2); }
  @ParameterizedTest(name = "quantity={0}") @ValueSource(ints = {1, 2})
  void preservesQuantity(int quantity) { assertEquals(quantity, Integer.parseInt(String.valueOf(quantity))); }
}
